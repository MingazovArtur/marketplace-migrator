"""
Pydantic-схемы API
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


# ========== Аутентификация ==========
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
                "password": "securePassword123",
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
    role: str = "user"
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


# ========== Характеристики товаров (ДО ProductBase!) ==========
class ProductAttributeBase(BaseModel):
    """Базовая схема характеристики товара"""
    name: str
    value: str
    platform_attribute_id: Optional[str] = None
    sort_order: int = 0


class ProductAttribute(ProductAttributeBase):
    """Схема характеристики товара (ответ)"""
    id: Optional[int] = None
    product_id: Optional[int] = None

    class Config:
        from_attributes = True


class ProductAttributeCreate(ProductAttributeBase):
    """Схема создания характеристики"""
    product_id: Optional[int] = None

# ========== Вариации товаров ==========
class ProductVariantBase(BaseModel):
    sku: str
    size: Optional[str] = None
    color: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    external_id: Optional[str] = None
    sort_order: int = 0


class ProductVariant(ProductVariantBase):
    id: Optional[int] = None
    product_id: Optional[int] = None

    class Config:
        from_attributes = True


class ProductVariantCreate(ProductVariantBase):
    product_id: Optional[int] = None

# ========== Товары ==========
class ProductBase(BaseModel):
    """Базовая схема товара"""
    name: str
    source: str
    price: float
    status: str = "pending"
    description: Optional[str] = ""
    photos_count: int = 0
    category: Optional[str] = "Не указана"
    mapped_category: Optional[str] = None
    sku: Optional[str] = None
    external_id: Optional[str] = None
    brand: Optional[str] = None
    photos: Optional[List[str]] = Field(default_factory=list)
    sku_count: int = 1
    attributes: Optional[List[ProductAttribute]] = Field(default_factory=list)
    variants: Optional[List[ProductVariant]] = Field(default_factory=list)


class Product(ProductBase):
    """Схема ответа (товар)"""
    id: Optional[int] = None
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductCreate(ProductBase):
    """Схема создания товара"""
    user_id: int
    attributes: Optional[List[ProductAttributeCreate]] = Field(default_factory=list)


class ProductBulkUpdate(BaseModel):
    """Массовое обновление товаров (цена / бренд / категория)"""
    product_ids: List[int]
    price: Optional[float] = None            # фиксированная новая цена
    price_percent: Optional[float] = None    # ИЛИ наценка в % к текущей цене
    brand: Optional[str] = None
    category: Optional[str] = None


# ========== Импорт / миграция ==========
class ImportRequest(BaseModel):
    url: str
    auth_key: str


class MigrateRequest(BaseModel):
    product_id: int
    target_marketplace: str
    edited_data: Optional[dict] = None


class BatchMigrateRequest(BaseModel):
    product_ids: List[int]
    target_marketplace: str


class Stats(BaseModel):
    total: int
    pending: int
    success: int
    error: int
    processing: int