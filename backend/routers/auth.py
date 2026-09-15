"""
Роутер для аутентификации: регистрация и логин
"""
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from database.session import SessionLocal
from database.models import User
from models.schemas import UserCreate, UserLogin, UserResponse, Token

# ИМПОРТИРУЕМ готовые функции из core.auth
from core.auth import get_password_hash, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Регистрация нового пользователя"""
    # Проверяем email
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    
    # Проверяем username
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username уже занят")
    
    # Создаем пользователя (используем импортированную функцию хэширования)
    new_user = User(
        email=user.email,
        username=user.username,
        hashed_password=get_password_hash(user.password)
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user


@router.post("/login", response_model=Token)
def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    """Вход пользователя и получение JWT токена"""
    user = db.query(User).filter(User.username == user_credentials.username).first()
    
    # Проверяем существование и корректность пароля
    if not user or not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Неверный username или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Создаем токен
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return {"access_token": access_token, "token_type": "bearer"}