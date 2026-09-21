"""
Роутеры email-жизненного цикла:
  - POST /api/auth/verify-email        — подтверждение email по JWT-токену
  - POST /api/auth/resend-verification — повторная отправка письма
  - POST /api/auth/forgot-password     — запрос сброса пароля (anti-enumeration: всегда 200)
  - POST /api/auth/reset-password      — сброс пароля по одноразовому токену

Rate-limits строгие: эти эндпоинты — любимая цель брутфорса и спам-бомбёжки.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from core.auth import decode_token, get_current_user, get_password_hash
from core.rate_limit import limiter
from database.access_log import get_client_ip, log_access
from database.models import User
from database.session import SessionLocal
from models.schemas import ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest
from services.email_service import (
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
    validate_reset_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Email"])


# ============================================================
# Подтверждение email
# ============================================================
@limiter.limit("10/hour")
@router.post("/verify-email")
async def verify_email(request: Request, payload: VerifyEmailRequest):
    """Подтверждение email по токену из письма."""
    data = decode_token(payload.token)
    if not data or data.get("type") != "verify":
        raise HTTPException(status_code=400, detail="Недействительная или просроченная ссылка")

    user_id = data.get("sub")
    email = data.get("email")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id), User.email == email).first()
        if not user:
            raise HTTPException(status_code=400, detail="Недействительная или просроченная ссылка")

        if user.email_verified_at is not None:
            return {"message": "Email уже подтверждён", "already_verified": True}

        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()

        ip = get_client_ip(request)
        ua = request.headers.get("user-agent")
        log_access(user_id=user.id, username=user.username, action="email_verified", ip=ip, user_agent=ua)
        logger.info(f"✅ Email подтверждён: {user.username}")

        # Приветственное письмо (не блокируем ответ, если упадёт)
        try:
            await send_welcome_email(user)
        except Exception as e:
            logger.warning(f"welcome email failed: {e}")

        return {"message": "Email подтверждён. Добро пожаловать!", "already_verified": False}
    finally:
        db.close()


# ============================================================
# Повторная отправка письма подтверждения
# ============================================================
@limiter.limit("3/hour")
@router.post("/resend-verification")
async def resend_verification(request: Request, current_user: User = Depends(get_current_user)):
    """Повторно отправить письмо подтверждения (макс. 3 раза в час)."""
    if current_user.email_verified_at is not None:
        raise HTTPException(status_code=400, detail="Email уже подтверждён")

    sent = await send_verification_email(current_user)
    if not sent:
        raise HTTPException(status_code=503, detail="Почтовый сервис временно недоступен")

    ip = get_client_ip(request)
    log_access(user_id=current_user.id, username=current_user.username,
               action="verification_resent", ip=ip, user_agent=request.headers.get("user-agent"))
    return {"message": "Письмо отправлено. Проверьте почту."}


# ============================================================
# Запрос сброса пароля (anti-enumeration)
# ============================================================
@limiter.limit("3/hour")
@router.post("/forgot-password")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    """
    Запрос сброса пароля.
    ВАЖНО: всегда возвращает 200 с одинаковым текстом — иначе злоумышленник
    сможет перечислять зарегистрированные email перебором.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == payload.email).first()
        if user:
            try:
                await send_password_reset_email(user)
                ip = get_client_ip(request)
                log_access(user_id=user.id, username=user.username,
                           action="password_reset_requested", ip=ip,
                           user_agent=request.headers.get("user-agent"))
            except Exception as e:
                logger.error(f"reset email failed for {user.email}: {e}")
    finally:
        db.close()

    # Одинаковый ответ независимо от существования email
    return {"message": "Если email зарегистрирован, мы отправили ссылку для сброса пароля."}


# ============================================================
# Сброс пароля по одноразовому токену
# ============================================================
@limiter.limit("5/hour")
@router.post("/reset-password")
async def reset_password(request: Request, payload: ResetPasswordRequest):
    """Сброс пароля по одноразовому токену из письма (TTL 1 час)."""
    user = validate_reset_token(payload.token)   # помечает токен как использованный
    if not user:
        raise HTTPException(status_code=400, detail="Ссылка недействительна, просрочена или уже использована")

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user.id).with_for_update().first()
        db_user.hashed_password = get_password_hash(payload.new_password)
        db.commit()

        ip = get_client_ip(request)
        log_access(user_id=db_user.id, username=db_user.username,
                   action="password_reset_completed", ip=ip, user_agent=request.headers.get("user-agent"))
        logger.info(f"🔑 Пароль сброшен: {db_user.username}")
        return {"message": "Пароль изменён. Войдите с новым паролем."}
    finally:
        db.close()