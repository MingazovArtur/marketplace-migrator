"""
Модуль аутентификации: хэширование паролей (bcrypt) и JWT токены
✅ v2: get_current_user переведён на неблокирующий AsyncSession + asyncpg
✅ v3: токен принимается из httpOnly-cookie ИЛИ из Authorization: Bearer
   (Bearer остаётся для программных клиентов и тестов); для cookie-сессий
   включена защита от CSRF (double-submit: заголовок X-CSRF-Token == куке).
"""

from datetime import timedelta

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY
from database.models import User
from database.session import get_async_db
from core.time import utcnow

security = HTTPBearer(auto_error=False)  # токен может прийти и из куки

# Имена кук: access_token — httpOnly (JS не читает), csrf_token — читается фронтендом
ACCESS_COOKIE = "access_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_password_hash(password: str) -> str:
    """Хэширует пароль с использованием bcrypt (с безопасным обрезанием до 72 байт)"""
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет соответствие пароля хэшу"""
    pwd_bytes = plain_password.encode("utf-8")
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]

    return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Создает JWT токен"""
    to_encode = data.copy()
    if expires_delta:
        expire = utcnow() + expires_delta
    else:
        expire = utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Декодирует JWT токен"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    except Exception:
        return None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    # 1) Токен: Authorization: Bearer ... (программные клиенты) или httpOnly-cookie
    token = credentials.credentials if credentials else request.cookies.get(ACCESS_COOKIE)
    cookie_auth = credentials is None  # авторизация через куку → нужна CSRF-защита

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2) CSRF (double-submit cookie): только для cookie-авторизации и только
    #    для изменяющих методов — Bearer-токен злоумышленник с чужого сайта
    #    подставить не может (не читается), а куку браузер шлёт сам.
    if cookie_auth and request.method not in SAFE_METHODS:
        csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
        csrf_header = request.headers.get(CSRF_HEADER, "")
        if not csrf_cookie or csrf_cookie != csrf_header:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF-проверка не пройдена",
            )

    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен: отсутствует sub",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен: некорректный sub",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalars().first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency для проверки роли администратора.
    Вызывает get_current_user, затем проверяет роль.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещен. Требуются права администратора.",
        )
    return current_user