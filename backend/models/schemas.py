"""
Pydantic-схемы API
"""

from datetime import datetime

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
    # ✅ v5: письмо о завершении пакетной миграции (вкл/выкл в меню профиля)
    notify_batch_done: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """Схема JWT токена"""

    access_token: str
    token_type: str = "bearer"
    # CSRF-токен для cookie-сессий (double-submit); в куке csrf_token он же
    csrf_token: str | None = None


class TokenData(BaseModel):
    """Данные внутри токена"""

    user_id: int | None = None


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
    platform_attribute_id: str | None = None
    sort_order: int = 0


class ProductAttribute(ProductAttributeBase):
    """Схема характеристики товара (ответ)"""

    id: int | None = None
    product_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductAttributeCreate(ProductAttributeBase):
    """Схема создания характеристики"""

    product_id: int | None = None


# ========== Вариации товаров ==========
class ProductVariantBase(BaseModel):
    sku: str
    size: str | None = None
    color: str | None = None
    price: float | None = None
    stock: int | None = None
    external_id: str | None = None
    sort_order: int = 0


class ProductVariant(ProductVariantBase):
    id: int | None = None
    product_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductVariantCreate(ProductVariantBase):
    product_id: int | None = None


# ========== Товары ==========
class ProductBase(BaseModel):
    """Базовая схема товара"""

    name: str
    source: str
    price: float
    status: str = "pending"
    description: str | None = ""
    photos_count: int = 0
    category: str | None = "Не указана"
    mapped_category: str | None = None
    sku: str | None = None
    external_id: str | None = None
    brand: str | None = None
    photos: list[str] | None = Field(default_factory=list)
    sku_count: int = 1
    stock: int | None = None
    attributes: list[ProductAttribute] | None = Field(default_factory=list)
    variants: list[ProductVariant] | None = Field(default_factory=list)

    # Логистические данные для экспорта на маркетплейсы (требования Ozon/Яндекс)
    barcode: str | None = None  # Штрихкод / EAN
    weight_grams: int | None = None  # Вес товара, г
    package_weight_grams: int | None = None  # Вес в упаковке, г
    package_width_mm: int | None = None  # Ширина упаковки, мм
    package_height_mm: int | None = None  # Высота упаковки, мм
    package_length_mm: int | None = None  # Длина упаковки, мм
    vat_rate: str | None = None  # НДС: none | 10 | 22 | 7 | 5
    okpd_code: str | None = None  # Код ОКПД/ТН ВЭД (маркировка)
    units_per_item: int | None = 1  # Единиц в одном товаре


class Product(ProductBase):
    """Схема ответа (товар)"""

    id: int | None = None
    user_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductCreate(ProductBase):
    """Схема создания товара"""

    user_id: int
    attributes: list[ProductAttributeCreate] | None = Field(default_factory=list)


class ProductBulkUpdate(BaseModel):
    """Массовое обновление товаров (цена / бренд / категория)"""

    product_ids: list[int]
    price: float | None = None  # фиксированная новая цена
    price_percent: float | None = None  # ИЛИ наценка в % к текущей цене
    brand: str | None = None
    category: str | None = None


class ProductLogisticsUpdate(BaseModel):
    """Обновление логистических данных товара: штрихкод, габариты упаковки, НДС, ОКПД."""

    barcode: str | None = None
    weight_grams: int | None = Field(None, ge=0)
    package_weight_grams: int | None = Field(None, ge=0)
    package_width_mm: int | None = Field(None, ge=0)
    package_height_mm: int | None = Field(None, ge=0)
    package_length_mm: int | None = Field(None, ge=0)
    vat_rate: str | None = None
    okpd_code: str | None = None
    units_per_item: int | None = Field(None, ge=1)

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
    url: str = ""
    auth_key: str = ""
    key: str = ""
    full_key: str = ""


class MigrateRequest(BaseModel):
    product_id: int
    target_marketplace: str
    edited_data: dict | None = None


class BatchMigrateRequest(BaseModel):
    product_ids: list[int]
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
    type: str  # number | text | select | multiselect
    required: bool = False
    group: str = "common"  # common | brand | variant | additional | fits_for
    values: list[str] | None = None
    case_sensitive: bool = True
    separator: str = ";"
    unit: str | None = None
    allow_unit_in_value: bool = False


class CategorySpecContent(BaseModel):
    sheets: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    attributes: list[CategoryAttributeSpec] = Field(default_factory=list)
    validation_rules: dict = Field(default_factory=dict)
    special_requirements: dict = Field(default_factory=dict)


class PlatformCategorySpecResponse(BaseModel):
    id: int
    user_id: int | None = None  # ✅ ИСПРАВЛЕНО: nullable в соответствии с моделью БД
    platform: str
    category_id: str
    category_name: str
    parent_category_id: str | None = None
    spec: CategorySpecContent
    fetched_at: datetime | None = None
    version: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CategorySpecListResponse(BaseModel):
    platform: str
    count: int
    specs: list[PlatformCategorySpecResponse]


class RefreshSpecRequest(BaseModel):
    """Запрос на обновление спеков через API площадки (требует ключ продавца)."""

    category_ids: list[str] | None = None
    api_key: str | None = None
    business_id: str | None = None
