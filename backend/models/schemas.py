"""
Pydantic-схемы API
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ========== Аутентификация ==========
class UserCreate(BaseModel):
    """Схема для регистрации нового пользователя"""
    email: EmailStr
    username: str
    password: str
    consent: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "username": "seller123",
                "password": "securePassword123",
                "consent": True,
            }
        }
    )


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
    email_verified_at: datetime | None = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """Схема JWT токена"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Данные внутри токена"""
    user_id: Optional[int] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)


class VerifyEmailRequest(BaseModel):
    token: str


# ========== Характеристики товаров ==========
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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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

    # ✅ Логистические данные для экспорта на маркетплейсы (требования Ozon/Яндекс)
    barcode: Optional[str] = None                    # Штрихкод / EAN
    weight_grams: Optional[int] = None               # Вес товара, г
    package_weight_grams: Optional[int] = None       # Вес в упаковке, г
    package_width_mm: Optional[int] = None           # Ширина упаковки, мм
    package_height_mm: Optional[int] = None          # Высота упаковки, мм
    package_length_mm: Optional[int] = None          # Длина упаковки, мм
    vat_rate: Optional[str] = None                   # НДС: none | 10 | 22
    okpd_code: Optional[str] = None                  # Код ОКПД/ТН ВЭД (маркировка)
    units_per_item: Optional[int] = 1                # Единиц в одном товаре


class Product(ProductBase):
    """Схема ответа (товар)"""
    id: Optional[int] = None
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


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


class ProductLogisticsUpdate(BaseModel):
    """Обновление логистических данных товара: штрихкод, габариты упаковки, НДС, ОКПД."""
    barcode: Optional[str] = None
    weight_grams: Optional[int] = Field(None, ge=0)
    package_weight_grams: Optional[int] = Field(None, ge=0)
    package_width_mm: Optional[int] = Field(None, ge=0)
    package_height_mm: Optional[int] = Field(None, ge=0)
    package_length_mm: Optional[int] = Field(None, ge=0)
    vat_rate: Optional[str] = None
    okpd_code: Optional[str] = None
    units_per_item: Optional[int] = Field(None, ge=1)

    # ✅ Синхронизация с модалкой и XLSX-генератором: Ozon принимает 5 ставок
    @field_validator("vat_rate")
    @classmethod
    def check_vat(cls, v):
        if v is not None and v not in ("none", "22", "10", "7", "5"):
            raise ValueError("НДС должен быть одним из: none, 22, 10, 7, 5")
        return v

    @field_validator("units_per_item")
    @classmethod
    def check_units(cls, v):
        if v is not None and v < 1:
            raise ValueError("Единиц в товаре должно быть >= 1")
        return v


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


# ========== Статистика ==========
class Stats(BaseModel):
    total: int
    pending: int
    success: int
    error: int
    processing: int

# ========== Спецификации категорий ==========
class CategoryAttributeSpec(BaseModel):
    id: str
    name: str
    type: str                    # number | text | select | multiselect
    required: bool = False
    group: str = "common"        # common | brand | variant | additional | fits_for
    values: Optional[List[str]] = None
    case_sensitive: bool = True
    separator: str = ";"
    unit: Optional[str] = None
    allow_unit_in_value: bool = False


class CategorySpecContent(BaseModel):
    sheets: List[str] = Field(default_factory=list)
    required_fields: List[str] = Field(default_factory=list)
    attributes: List[CategoryAttributeSpec] = Field(default_factory=list)
    validation_rules: dict = Field(default_factory=dict)
    special_requirements: dict = Field(default_factory=dict)


class PlatformCategorySpecResponse(BaseModel):
    id: int
    user_id: int
    platform: str
    category_id: str
    category_name: str
    parent_category_id: Optional[str] = None
    spec: CategorySpecContent
    fetched_at: datetime
    version: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CategorySpecListResponse(BaseModel):
    platform: str
    count: int
    specs: List[PlatformCategorySpecResponse]


class RefreshSpecRequest(BaseModel):
    """Запрос на обновление спеков через API площадки (требует ключ продавца)."""
    category_ids: Optional[List[str]] = None
    api_key: Optional[str] = None
    business_id: Optional[str] = None 