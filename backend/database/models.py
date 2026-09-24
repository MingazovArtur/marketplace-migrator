"""
Модели базы данных SQLAlchemy
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, func, Index, UniqueConstraint, JSON
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime




Base = declarative_base()


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"
    email_verified_at = Column(DateTime, nullable=True)   # когда подтвердил email
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String, default="user", nullable=False)  # "user" или "admin"
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="owner")

class AccessLog(Base):
    """Журнал доступа: кто, когда, с какого IP (152-ФЗ / безопасность)."""
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(100), nullable=True)
    action = Column(String(50), nullable=False)   # register | consent_accepted | login_success | login_failed | logout
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class Category(Base):
    """Справочник категорий маркетплейсов"""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, nullable=False)
    category_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    parent_id = Column(String, nullable=True)
    full_path = Column(String, nullable=True)
    level = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    

    __table_args__ = (
        Index('idx_platform_category', 'platform', 'category_id'),
    )


class CategoryMapping(Base):
    """Маппинг категорий между площадками"""
    __tablename__ = "category_mappings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_platform = Column(String, nullable=False)
    source_category_id = Column(String, nullable=False)
    target_platform = Column(String, nullable=False)
    target_category_id = Column(String, nullable=False)
    confidence = Column(Float, default=1.0)
    is_manual = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_mapping_lookup', 'source_platform', 'source_category_id', 'target_platform'),
    )

class Product(Base):
    """Модель товара (расширенная под богатую модель данных)"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String, default="pending", index=True)       # ← index=True
    description = Column(String, default="")
    photos_count = Column(Integer, default=0)
    category = Column(String, default="Не указана")
    mapped_category = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    barcode = Column(String, nullable=True)                     # Штрихкод / EAN
    weight_grams = Column(Integer, nullable=True)               # Вес товара, г
    package_weight_grams = Column(Integer, nullable=True)       # Вес в упаковке, г
    package_width_mm = Column(Integer, nullable=True)           # Ширина упаковки, мм
    package_height_mm = Column(Integer, nullable=True)          # Высота упаковки, мм
    package_length_mm = Column(Integer, nullable=True)          # Длина упаковки, мм
    vat_rate = Column(String, nullable=True)                    # НДС: none | 10 | 22
    okpd_code = Column(String, nullable=True)                   # Код ОКПД/ТН ВЭД (маркировка)
    units_per_item = Column(Integer, nullable=True, default=1)  # Единиц в одном товаре
    created_at = Column(DateTime, default=datetime.utcnow)

    # --- Богатая модель данных ---
    sku = Column(String, nullable=True, index=True)
    external_id = Column(String, nullable=True, index=True)
    brand = Column(String, nullable=True)
    photos = Column(JSON, default=list)
    sku_count = Column(Integer, default=1)
    stock = Column(Integer, nullable=True)                        # ← ДОБАВЛЕНО
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # ← ДОБАВЛЕНО

    owner = relationship("User", back_populates="products")
    attributes = relationship("ProductAttribute", back_populates="product", cascade="all, delete-orphan")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

class ProductAttribute(Base):
    """Характеристика товара (Размер, Цвет, Материал и т.д.)"""
    __tablename__ = "product_attributes"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)              # "Размер", "Цвет", "Материал"
    value = Column(String, nullable=False)              # "XL", "Красный", "Хлопок"
    platform_attribute_id = Column(String, nullable=True)  # ID характеристики на площадке (для Ozon/WB)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связь с товаром
    product = relationship("Product", back_populates="attributes")

    __table_args__ = (
        Index('idx_product_attr_name', 'product_id', 'name'),
)

class ProductVariant(Base):
    """Вариация товара (отдельный SKU: размер/цвет/цена/остаток)"""
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    sku = Column(String, nullable=False, index=True)        # ШК/артикул варианта
    size = Column(String, nullable=True)                     # "92", "XL"
    color = Column(String, nullable=True)                    # "Розовый"
    price = Column(Float, nullable=True)
    stock = Column(Integer, nullable=True)
    external_id = Column(String, nullable=True)              # ID варианта на площадке
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="variants")

    __table_args__ = (
        Index('idx_variant_product_sku', 'product_id', 'sku'),
)

class FileOperationLog(Base):
    """Журнал операций импорта/экспорта файлов"""
    __tablename__ = "file_operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    operation = Column(String, nullable=False)   # import_file | import_api | import_yml | export
    platform = Column(String, nullable=True)
    filename = Column(String, nullable=True)
    mode = Column(String, nullable=True)         # create | upsert
    status = Column(String, default="success")   # success | partial | error
    total_rows = Column(Integer, default=0)
    imported = Column(Integer, default=0)
    updated = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    errors = Column(JSON, default=list)          # первые N ошибок
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class MigrationLog(Base):
    """Журнал миграций товаров"""
    __tablename__ = "migration_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    product_name = Column(String, nullable=True)
    source_platform = Column(String, nullable=True)
    target_platform = Column(String, nullable=False)
    old_price = Column(Float, nullable=True)
    new_price = Column(Float, nullable=True)
    old_category = Column(String, nullable=True)
    new_category = Column(String, nullable=True)
    status = Column(String, default="success")   # success | error
    error_message = Column(String, nullable=True)
    is_batch = Column(Boolean, default=False)
    batch_id = Column(String, nullable=True)     # task_id для группировки пакета
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

class ImportExportStats(Base):
    """Статистика операций (импорт/экспорт/миграция) для дашборда"""
    __tablename__ = "import_export_stats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    operation = Column(String, nullable=False, index=True)  # import_file | import_api | import_yml | export | migrate | media_download
    platform = Column(String, nullable=True)
    status = Column(String, default="success")   # success | partial | error
    total_items = Column(Integer, default=0)     # строк/товаров в операции
    success_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)     # время обработки, мс
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

class PasswordResetToken(Base):
    """Одноразовый токен сброса пароля (TTL 1 час)."""
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    token_hash = Column(String(64), nullable=False, unique=True)   # SHA-256 от токена
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", backref="reset_tokens")

class PlatformCategorySpec(Base):
    """
    Спецификация категории площадки: обязательные поля, атрибуты, словари значений.
    Источник: официальный API площадки.

    ✅ ГЛОБАЛЬНЫЙ справочник: структура категорий площадки одинакова для всех
    продавцов, поэтому строка одна на пару (platform, category_id).
    user_id — только аудит: кто загрузил/обновил спек (nullable).
    """
    __tablename__ = "platform_category_specs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # кто загрузил (аудит)
    platform = Column(String, nullable=False, index=True)              # ozon | yandex | wildberries
    category_id = Column(String, nullable=False, index=True)           # id категории на площадке
    category_name = Column(String, nullable=False)                     # человекочитаемое имя
    parent_category_id = Column(String, nullable=True)                 # родительская категория
    spec = Column(JSON, nullable=False, default=dict)                  # вся спека (см. ниже структуру)
    fetched_at = Column(DateTime, default=datetime.utcnow)             # когда подтянули с API
    version = Column(String, nullable=True)                            # хэш для детекта изменений

    user = relationship("User", backref="category_specs")

    __table_args__ = (
        UniqueConstraint("platform", "category_id", name="uq_platform_category"),
    )