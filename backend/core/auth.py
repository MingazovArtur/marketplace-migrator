"""
Модуль аутентификации: хэширование паролей (bcrypt) и JWT токены
"""
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database.session import SessionLocal
from database.models import User
from core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

security = HTTPBearer()


def get_password_hash(password: str) -> str:
    """Хэширует пароль с использованием bcrypt (с безопасным обрезанием до 72 байт)"""
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет соответствие пароля хэшу"""
    pwd_bytes = plain_password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    
    return bcrypt.checkpw(pwd_bytes, hashed_password.encode('utf-8'))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создает JWT токен"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Декодирует JWT токен"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        # 🔍 Печатаем точную причину ошибки от библиотеки jose
        print(f"❌ [JWT DEBUG] Ошибка декодирования: {type(e).__name__} - {e}")
        print(f"❌ [JWT DEBUG] Проблемный токен (первые 50 символов): '{token[:50]}...'")
        return None
    except Exception as e:
        print(f"❌ [JWT DEBUG] Неожиданная ошибка: {e}")
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Dependency для получения текущего пользователя из токена"""
    token = credentials.credentials
    print(f"🔍 [AUTH DEBUG] Получен токен: {token[:30]}...")
    
    payload = decode_token(token)
    if payload is None:
        print("❌ [AUTH DEBUG] Ошибка декодирования токена (неверная подпись или истек)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = int(payload.get("sub")) # Явно преобразуем строку обратно в число для БД
    if user_id is None:
        print("❌ [AUTH DEBUG] В токене отсутствует поле 'sub'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    print(f"🔍 [AUTH DEBUG] Извлечен user_id из токена: {user_id}")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            print(f"❌ [AUTH DEBUG] КРИТИЧЕСКАЯ ОШИБКА: Пользователь с id={user_id} НЕ НАЙДЕН в базе данных!")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        print(f"✅ [AUTH DEBUG] Успешно: пользователь '{user.username}' (id={user.id}) авторизован")
        return user
    finally:
        db.close()