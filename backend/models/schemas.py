from pydantic import BaseModel
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class BatchMigrateRequest(BaseModel): product_ids: List[int]; target_marketplace: str

class Product(BaseModel):
    id: Optional[int] = None  # <-- СДЕЛАЛИ ОПЦИОНАЛЬНЫМ, чтобы репозиторий мог назначить его сам
    name: str
    source: str
    price: float
    status: str = "pending"
    description: Optional[str] = ""
    photos_count: int = 0
    category: Optional[str] = None
    mapped_category: Optional[str] = None

class ImportRequest(BaseModel):
    url: str
    auth_key: str

class MigrateRequest(BaseModel):
    product_id: int
    target_marketplace: str

class Stats(BaseModel):
    total: int
    pending: int
    success: int
    error: int
    processing: int

class ProductCreate(BaseModel):
    name: str
    source: str
    price: float
    status: str = "pending"
    description: str = ""
    photos_count: int = 0
    category: str = "Не указана"
    mapped_category: Optional[str] = None
    user_id: int  # <-- Убедитесь, что это поле здесь есть

# === Схемы для аутентификации ===

class UserCreate(BaseModel):
    """Схема для регистрации нового пользователя"""
    email: EmailStr
    username: str
    password: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "username": "seller123",
                "password": "securePassword123"
            }
        }


class UserLogin(BaseModel):
    """Схема для входа"""
    username: str
    password: str


class UserResponse(BaseModel):
    """Схема ответа с данными пользователя"""
    id: int
    email: str
    username: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """Схема JWT токена"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Данные внутри токена"""
    user_id: Optional[int] = None