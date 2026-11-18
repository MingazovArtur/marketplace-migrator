"""
Роутер аутентификации (регистрация, вход, профиль)

B-1 (неделя 2): register/login/logout — sync def. FastAPI выполняет такие
роуты в threadpool, поэтому bcrypt (~100-300 мс CPU) и синхронные запросы к БД
больше НЕ блокируют event loop. Асинхронность внутри не используется
(кроме background-задачи — Starlette умеет await async-колбэки и из sync-роут).
"""

import logging
import secrets
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from core.config import settings
from core.rate_limit import limiter, revoke_token
from database.access_log import get_client_ip, log_access
from database.models import User
from database.session import SessionLocal, get_db
from models.schemas import Token, UserCreate, UserLogin, UserResponse
from services.demo_data import DEMO_USERNAME, ensure_demo_user, reset_demo_if_stale
from services.email_service import send_verification_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])
security = HTTPBearer()


class NotificationsUpdate(BaseModel):
    """Настройки уведомлений (пока одна — письмо о пакете)."""

    notify_batch_done: bool | None = None


# ============================================================
# Регистрация: 10 попыток в день на идентификатор (IP или user_id)
# ============================================================
@limiter.limit("10/day")
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
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
        try:
            db.commit()
        except IntegrityError:
            # R35 (В-4): гонка «проверил email → INSERT» между параллельными
            # регистрациями решается на уровне БД — unique-констрейнты не
            # пускают дубль; здесь остаётся вернуть понятный 400 вместо
            # общего 500 «Ошибка при регистрации».
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким email или логином уже существует",
            ) from None
        db.refresh(user)

        # Логирование регистрации и согласия
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

        logger.info(f"Зарегистрирован пользователь: {user.username} (id={user.id})")

        # Отправка письма подтверждения (в фоне, после ответа клиенту).
        # Детачим значения пользователя от сессии, чтобы background task
        # работал после db.close()
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
        ) from e
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
        logger.info(f"Вход выполнен: {user.username}")

        # Куки: access_token — httpOnly (JS не может прочитать токен — защита от XSS-кражи),
        # csrf_token — читается фронтендом и возвращается заголовком X-CSRF-Token (double-submit).
        # R35: имена кук — константы ACCESS_COOKIE/CSRF_COOKIE из core/auth.py
        # (раньше те же строки были продублированы литералами в трёх местах).
        csrf_token = secrets.token_urlsafe(32)
        max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        response = JSONResponse(
            content={"access_token": token, "token_type": "bearer", "csrf_token": csrf_token}
        )
        response.set_cookie(
            ACCESS_COOKIE,
            token,
            max_age=max_age,
            httponly=True,
            samesite=settings.COOKIE_SAMESITE,
            secure=settings.COOKIE_SECURE,
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE,
            csrf_token,
            max_age=max_age,
            httponly=False,
            samesite=settings.COOKIE_SAMESITE,
            secure=settings.COOKIE_SECURE,
            path="/",
        )
        return response

    finally:
        db.close()


# ============================================================
# Демо-вход: общий демо-аккаунт без регистрации. Данные подложены
# и сбрасываются раз в сутки (services/demo_data.py). 30/день —
# демонстрацию не выкачивают, но и брутфорс-поле не открывают.
# ============================================================
@limiter.limit("30/day")
@router.post("/demo", response_model=Token)
def demo_login(request: Request):
    """Вход в демо-аккаунт: без пароля и регистрации.

    Общий аккаунт `demo` с подложенными товарами и историей. Отключается
    админом деактивацией пользователя demo (is_active=False) — токены
    деактивированного аккаунта отклоняются get_current_user сразу.
    """
    db = SessionLocal()
    try:
        user = ensure_demo_user(db)
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Демо-доступ временно отключён администратором",
            )
        reset_demo_if_stale(db, user)

        ip = get_client_ip(request)
        ua = request.headers.get("user-agent")
        log_access(
            user_id=user.id, username=user.username, action="demo_login", ip=ip, user_agent=ua
        )
        token = create_access_token({"sub": str(user.id), "role": user.role})
        logger.info(f"Демо-вход (id={user.id}, username={DEMO_USERNAME})")

        # Куки — ровно как у обычного логина (httpOnly access + csrf double-submit)
        csrf_token = secrets.token_urlsafe(32)
        max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        response = JSONResponse(
            content={"access_token": token, "token_type": "bearer", "csrf_token": csrf_token}
        )
        response.set_cookie(
            ACCESS_COOKIE,
            token,
            max_age=max_age,
            httponly=True,
            samesite=settings.COOKIE_SAMESITE,
            secure=settings.COOKIE_SECURE,
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE,
            csrf_token,
            max_age=max_age,
            httponly=False,
            samesite=settings.COOKIE_SAMESITE,
            secure=settings.COOKIE_SECURE,
            path="/",
        )
        return response
    finally:
        db.close()


# ============================================================
# Логаут: 10 в минуту (защита от флуда)
# ============================================================
@limiter.limit("10/minute")
@router.post("/logout")
def logout(request: Request, response: Response, current_user: User = Depends(get_current_user)):
    """Выход: отзыв токена по jti (R35, К-3), логирование и очистка кук."""
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent")
    log_access(
        user_id=current_user.id,
        username=current_user.username,
        action="logout",
        ip=ip,
        user_agent=ua,
    )

    # R35 (К-3): logout больше не «просто стёр куку» — токен отзывается по
    # jti (блэклист в Redis на остаток его жизни), поэтому и украденная
    # копия этого же access-токена тоже умрёт (проверка — get_current_user).
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    else:
        token = request.cookies.get(ACCESS_COOKIE)
    if token:
        from core.auth import get_jwt_payload_cached

        # get_current_user уже декодировал этот токен — берём из кэша
        payload = get_jwt_payload_cached(request, token) or {}
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            try:
                revoke_token(jti, int(exp - time.time()))
            except Exception as e:
                # Redis недоступен: logout не должен 500-ить, но факт
                # «токен НЕ отозван и доживёт до exp» обязан попасть в лог
                logger.error(f"Не удалось отозвать токен (jti={str(jti)[:8]}…): {e}")

    logger.info(f"Выход: {current_user.username}")
    # Сбрасываем обе куки. Атрибуты path/samesite/secure повторяют
    # установку: часть браузеров матчит куку на удаление по ним (R35).
    response.delete_cookie(
        ACCESS_COOKIE, path="/", samesite=settings.COOKIE_SAMESITE, secure=settings.COOKIE_SECURE
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", samesite=settings.COOKIE_SAMESITE, secure=settings.COOKIE_SECURE
    )
    return {"message": "Вы вышли из системы"}


# ============================================================
# Профиль: без собственного лимита — покрыт общим 200/min
# (default_limits в core/rate_limit.py, R29)
# ============================================================
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Текущий авторизованный пользователь"""
    return current_user


@router.get("/notifications")
async def get_notifications(current_user: User = Depends(get_current_user)):
    """Настройки уведомлений пользователя."""
    return {
        "notify_batch_done": bool(current_user.notify_batch_done),
        "email": current_user.email,
        "email_verified": bool(current_user.email_verified_at),
    }


@router.put("/notifications")
async def update_notifications(
    payload: NotificationsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Включить/выключить письмо о завершении пакетной миграции."""
    if payload.notify_batch_done is None:
        raise HTTPException(status_code=400, detail="Не указаны настройки для обновления")

    current_user.notify_batch_done = bool(payload.notify_batch_done)
    db.commit()
    db.refresh(current_user)
    return {"success": True, "notify_batch_done": bool(current_user.notify_batch_done)}
