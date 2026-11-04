"""
Роутер аутентификации (регистрация, вход, профиль)

B-1 (неделя 2): register/login/logout — sync def. FastAPI выполняет такие
роуты в threadpool, поэтому bcrypt (~100-300 мс CPU) и синхронные запросы к БД
больше НЕ блокируют event loop. Асинхронность внутри не используется
(кроме background-задачи — Starlette умеет await async-колбэки и из sync-роут).
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from core.auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from core.rate_limit import limiter
from database.access_log import get_client_ip, log_access
from database.models import User
from database.session import SessionLocal
from models.schemas import Token, UserCreate, UserLogin, UserResponse
from services.email_service import send_verification_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])
security = HTTPBearer()


# ============================================================
# Регистрация: 10 попыток в день на идентификатор (IP или user_id)
# ============================================================
@limiter.limit("10/day")
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,  # ← добавлено
):
    """Регистрация нового пользователя с логированием доступа и отправкой письма подтверждения."""
    if len(payload.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пароль должен содержать минимум 6 символов",
        )

    db = SessionLocal()
    try:
        # Проверка уникальности email
        if db.query(User).filter(User.email == payload.email).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким email уже существует",
            )
        # Проверка уникальности username
        if db.query(User).filter(User.username == payload.username).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким логином уже существует",
            )

        # Создаём пользователя
        hashed_password = get_password_hash(payload.password)
        user = User(
            email=payload.email,
            username=payload.username,
            hashed_password=hashed_password,
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # ✅ Логирование регистрации и согласия
        ip = get_client_ip(request)
        ua = request.headers.get("user-agent")
        log_access(user_id=user.id, username=user.username, action="register", ip=ip, user_agent=ua)
        if payload.consent:
            log_access(
                user_id=user.id,
                username=user.username,
                action="consent_accepted",
                ip=ip,
                user_agent=ua,
            )

        logger.info(f"✅ Зарегистрирован пользователь: {user.username} (id={user.id})")

        # ✅ Отправка письма подтверждения (в фоне, после ответа клиенту)
        # Детачим значения пользователя от сессии, чтобы background task работал после db.close()
        user_snapshot = {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        }

        async def _safe_send():
            try:
                # Перечитываем пользователя в background-контексте (новая сессия)
                bg_db = SessionLocal()
                try:
                    bg_user = bg_db.query(User).filter(User.id == user_snapshot["id"]).first()
                    if bg_user:
                        await send_verification_email(bg_user)
                finally:
                    bg_db.close()
            except Exception as e:
                logger.error(
                    f"📧 ❌ Не удалось отправить письмо подтверждения {user_snapshot['email']}: {e}"
                )

        background_tasks.add_task(_safe_send)

        return user

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка регистрации: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при регистрации",
        )
    finally:
        db.close()


# ============================================================
# Логин: 5 попыток в минуту (защита от брутфорса)
# ============================================================
@limiter.limit("5/minute")
@router.post("/login", response_model=Token)
def login(payload: UserLogin, request: Request):
    """Вход: возвращает JWT-токен с логированием"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == payload.username).first()
        ip = get_client_ip(request)
        ua = request.headers.get("user-agent")

        if not user or not verify_password(payload.password, user.hashed_password):
            log_access(username=payload.username, action="login_failed", ip=ip, user_agent=ua)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный логин или пароль",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Аккаунт деактивирован",
            )

        log_access(
            user_id=user.id, username=user.username, action="login_success", ip=ip, user_agent=ua
        )
        token = create_access_token({"sub": str(user.id), "role": user.role})
        logger.info(f"✅ Вход выполнен: {user.username}")
        return {"access_token": token, "token_type": "bearer"}

    finally:
        db.close()


# ============================================================
# Логаут: 10 в минуту (защита от флуда)
# ============================================================
@limiter.limit("10/minute")
@router.post("/logout")
def logout(request: Request, current_user: User = Depends(get_current_user)):
    """Выход с логированием"""
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent")
    log_access(
        user_id=current_user.id,
        username=current_user.username,
        action="logout",
        ip=ip,
        user_agent=ua,
    )
    logger.info(f"👋 Выход: {current_user.username}")
    return {"message": "Вы вышли из системы"}


# ============================================================
# Профиль: без лимитов (покрывается глобальным 100/min из middleware)
# ============================================================
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Текущий авторизованный пользователь"""
    return current_user
