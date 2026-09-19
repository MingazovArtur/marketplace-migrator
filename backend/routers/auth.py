"""
Роутер аутентификации (регистрация, вход, профиль)
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from database.session import SessionLocal
from database.models import User
from database.access_log import log_access, get_client_ip
from core.auth import (
    get_current_user,
    create_access_token,
    get_password_hash,
    verify_password,
)
from models.schemas import UserCreate, UserLogin, UserResponse, Token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])
security = HTTPBearer()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, request: Request):
    """Регистрация нового пользователя с логированием доступа"""
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
            log_access(user_id=user.id, username=user.username, action="consent_accepted", ip=ip, user_agent=ua)

        logger.info(f"✅ Зарегистрирован пользователь: {user.username} (id={user.id})")
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


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, request: Request):
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

        log_access(user_id=user.id, username=user.username, action="login_success", ip=ip, user_agent=ua)
        token = create_access_token({"sub": str(user.id), "role": user.role})
        logger.info(f"✅ Вход выполнен: {user.username}")
        return {"access_token": token, "token_type": "bearer"}

    finally:
        db.close()


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), request: Request):
    """Выход с логированием"""
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent")
    log_access(user_id=current_user.id, username=current_user.username, action="logout", ip=ip, user_agent=ua)
    logger.info(f"👋 Выход: {current_user.username}")
    return {"message": "Вы вышли из системы"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Текущий авторизованный пользователь"""
    return current_user