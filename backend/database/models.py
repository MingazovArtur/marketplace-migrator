"""
Модели базы данных SQLAlchemy
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

from core.time import utcnow

# P-1 (неделя 3): денежные поля хранятся как NUMERIC(12,2).
# FLOAT двоичный — цены типа 19.99 копятся с ошибкой (sum → 199.89999999999998).
# 12,2 покрывает суммы до 9 999 999 999.99 ₽; БД считает/суммирует точно.
MONEY = Numeric(12, 2)

Base = declarative_base()


class User(Base):
    """Модель пользователя"""

    __tablename__ = "users"
    email_verified_at = Column(DateTime, nullable=True)  # когда подтвердил email
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String, default="user", nullable=False)  # "user" или "admin"
    # ✅ v5: слать ли письмо о завершении пакетной миграции
    notify_batch_done = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow)

    products = relationship("Product", back_populates="owner")


class AccessLog(Base):
    """Журнал доступа: кто, когда, с какого IP (152-ФЗ / безопасность)."""

    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(100), nullable=True)
    action = Column(
        String(50), nullable=False
    )  # register | consent_accepted | login_success | login_failed | logout
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
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (Index("idx_platform_category", "platform", "category_id"),)


class CategoryMapping(Base):
    """Маппинг категорий между площадками"""

    __tablename__ = "category_mappings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_platform = Column(String, nullable=False)
    source_category_id = Column(String, nullable=False)
    target_platform = Column(String, nullable=False)
    target_category_id = Column(String, nullable=False)
    confidence = Column(Float, default=1.0)  # не деньги: 0..1 — Float корректен
    is_manual = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("idx_mapping_lookup", "source_platform", "source_category_id", "target_platform"),
    )


class Product(Base):
    """Модель товара (расширенная под богатую модель данных)"""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)
    price = Column(MONEY, nullable=False)  # P-1: было Float
    status = Column(String, default="pending", index=True)  # ← index=True
    description = Column(String, default="")
    photos_count = Column(Integer, default=0)
    category = Column(String, default="Не указана")
    mapped_category = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    barcode = Column(String, nullable=True)  # Штрихкод / EAN
    weight_grams = Column(Integer, nullable=True)  # Вес товара, г
    package_weight_grams = Column(Integer, nullable=True)  # Вес в упаковке, г
    package_width_mm = Column(Integer, nullable=True)  # Ширина упаковки, мм
    package_height_mm = Column(Integer, nullable=True)  # Высота упаковки, мм
    package_length_mm = Column(Integer, nullable=True)  # Длина упаковки, мм
    vat_rate = Column(String, nullable=True)  # НДС: none | 10 | 22
    okpd_code = Column(String, nullable=True)  # Код ОКПД/ТН ВЭД (маркировка)
    units_per_item = Column(Integer, nullable=True, default=1)  # Единиц в одном товаре
    created_at = Column(DateTime, default=utcnow)

    # --- Богатая модель данных ---
    sku = Column(String, nullable=True, index=True)
    external_id = Column(String, nullable=True, index=True)
    brand = Column(String, nullable=True)
    photos = Column(JSON, default=list)
    sku_count = Column(Integer, default=1)
    stock = Column(Integer, nullable=True)  # ← ДОБАВЛЕНО
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)  # ← ДОБАВЛЕНО

    # ✅ v4 (инкрементальный экспорт): когда и на какую площадку товар
    # выгружался в последний раз. «Только изменённые» = updated_at > last_export_at
    # либо товар ещё не выгружался вовсе.
    last_export_at = Column(DateTime, nullable=True)
    last_export_platform = Column(String, nullable=True)

    owner = relationship("User", back_populates="products")
    attributes = relationship(
        "ProductAttribute", back_populates="product", cascade="all, delete-orphan"
    )
    variants = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan"
    )


class ProductAttribute(Base):
    """Характеристика товара (Размер, Цвет, Материал и т.д.)"""

    __tablename__ = "product_attributes"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String, nullable=False)  # "Размер", "Цвет", "Материал"
    value = Column(String, nullable=False)  # "XL", "Красный", "Хлопок"
    platform_attribute_id = Column(
        String, nullable=True
    )  # ID характеристики на площадке (для Ozon/WB)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    # Связь с товаром
    product = relationship("Product", back_populates="attributes")

    __table_args__ = (Index("idx_product_attr_name", "product_id", "name"),)


class ProductVariant(Base):
    """Вариация товара (отдельный SKU: размер/цвет/цена/остаток)"""

    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sku = Column(String, nullable=False, index=True)  # ШК/артикул варианта
    size = Column(String, nullable=True)  # "92", "XL"
    color = Column(String, nullable=True)  # "Розовый"
    price = Column(MONEY, nullable=True)  # P-1: было Float
    stock = Column(Integer, nullable=True)
    external_id = Column(String, nullable=True)  # ID варианта на площадке
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    product = relationship("Product", back_populates="variants")

    __table_args__ = (Index("idx_variant_product_sku", "product_id", "sku"),)


class FileOperationLog(Base):
    """Журнал операций импорта/экспорта файлов"""

    __tablename__ = "file_operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    operation = Column(String, nullable=False)  # import_file | import_api | import_yml | export
    platform = Column(String, nullable=True)
    filename = Column(String, nullable=True)
    mode = Column(String, nullable=True)  # create | upsert
    status = Column(String, default="success")  # success | partial | error
    total_rows = Column(Integer, default=0)
    imported = Column(Integer, default=0)
    updated = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    errors = Column(JSON, default=list)  # первые N ошибок
    created_at = Column(DateTime, default=utcnow, index=True)


class MigrationLog(Base):
    """Журнал миграций товаров"""

    __tablename__ = "migration_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    product_name = Column(String, nullable=True)
    source_platform = Column(String, nullable=True)
    target_platform = Column(String, nullable=False)
    old_price = Column(MONEY, nullable=True)  # P-1: было Float
    new_price = Column(MONEY, nullable=True)  # P-1: было Float
    old_category = Column(String, nullable=True)
    new_category = Column(String, nullable=True)
    status = Column(String, default="success")  # success | error
    error_message = Column(String, nullable=True)
    is_batch = Column(Boolean, default=False)
    batch_id = Column(String, nullable=True)  # task_id для группировки пакета
    created_at = Column(DateTime, default=utcnow, index=True)


class ImportExportStats(Base):
    """Статистика операций (импорт/экспорт/миграция) для дашборда"""

    __tablename__ = "import_export_stats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    operation = Column(
        String, nullable=False, index=True
    )  # import_file | import_api | import_yml | export | migrate | media_download
    platform = Column(String, nullable=True)
    status = Column(String, default="success")  # success | partial | error
    total_items = Column(Integer, default=0)  # строк/товаров в операции
    success_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)  # время обработки, мс
    created_at = Column(DateTime, default=utcnow, index=True)


class PasswordResetToken(Base):
    """Одноразовый токен сброса пароля (TTL 1 час)."""

    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    token_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 от токена
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
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )  # кто загрузил (аудит)
    platform = Column(String, nullable=False, index=True)  # ozon | yandex | wildberries
    category_id = Column(String, nullable=False, index=True)  # id категории на площадке
    category_name = Column(String, nullable=False)  # человекочитаемое имя
    parent_category_id = Column(String, nullable=True)  # родительская категория
    spec = Column(JSON, nullable=False, default=dict)  # вся спека (см. ниже структуру)
    fetched_at = Column(DateTime, default=utcnow)  # когда подтянули с API
    version = Column(String, nullable=True)  # хэш для детекта изменений

    user = relationship("User", backref="category_specs")

    __table_args__ = (UniqueConstraint("platform", "category_id", name="uq_platform_category"),)


class ExportDefault(Base):
    """
    Дефолты экспорта: глобальные (category_name=NULL) и по категориям.

    Применяются при массовом дозаполнении пропусков и при миграции:
    только ПУСТЫЕ/нулевые поля товара заполняются из дефолтов.
    Уже указанные значения не перезаписываются.
    """

    __tablename__ = "export_defaults"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_name = Column(String, nullable=True)  # NULL = глобальные
    vat_rate = Column(String, nullable=True)  # none/22/10/7/5
    okpd_code = Column(String, nullable=True)  # ТН ВЭД
    package_weight_grams = Column(Integer, nullable=True)
    package_width_mm = Column(Integer, nullable=True)
    package_height_mm = Column(Integer, nullable=True)
    package_length_mm = Column(Integer, nullable=True)
    brand = Column(String, nullable=True)  # значение бренда по умолчанию
    marking = Column(String, nullable=True, default="Нет")  # Нужен код маркировки
    price_default = Column(
        Numeric(10, 2), nullable=True
    )  # ✅ цена по умолчанию (только для нулевых)

    __table_args__ = (
        UniqueConstraint("user_id", "category_name", name="uq_export_defaults_user_category"),
    )


class MigrationProfile(Base):
    """
    ✅ v4: профиль миграции — типовой набор «площадка + дефолты», чтобы
    повторять частую миграцию в один клик.

    Применение (POST /migration-profiles/{id}/apply) проставляет сохранённые
    значения как ГЛОБАЛЬНЫЕ дефолты пользователя (ExportDefault, category=NULL)
    и возвращает площадку — фронт подставляет её в окно миграции.
    """

    __tablename__ = "migration_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(200), nullable=False)
    platform = Column(String, nullable=False)  # ozon | wildberries | yandex | ...
    # Снимок дефолтов на момент создания профиля (те же поля, что ExportDefault)
    vat_rate = Column(String, nullable=True)
    okpd_code = Column(String, nullable=True)
    package_weight_grams = Column(Integer, nullable=True)
    package_width_mm = Column(Integer, nullable=True)
    package_height_mm = Column(Integer, nullable=True)
    package_length_mm = Column(Integer, nullable=True)
    brand = Column(String, nullable=True)
    marking = Column(String, nullable=True, default="Нет")
    price_default = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    user = relationship("User", backref="migration_profiles")

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_migration_profile_user_name"),)


class BulkEditSnapshot(Base):
    """
    Снапшот значений перед операцией правки товаров (undo «Отменить»).

    ✅ v4 (аудит-лог + undo): пишется ЛЮБОЙ правкой — массовым обновлением,
    одиночной правкой, логистикой, массовым подбором ТН ВЭД, дозаполнением
    дефолтов. Для каждого затронутого товара сохраняются прежние значения
    РОВНО тех полей, которые менялись (payload.fields). POST /products/undo
    восстанавливает значения из выбранного (или последнего неотменённого)
    снапшота.

    Ротация: хранятся последние SNAPSHOTS_PER_USER (см. services/edit_history.py)
    — старые удаляются, чтобы таблица не росла бесконечно.
    """

    __tablename__ = "bulk_edit_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime, default=utcnow)
    # Тип операции для истории: bulk_update | edit | logistics | tnved | defaults
    action = Column(String(40), nullable=False, default="bulk_update")
    # Человекочитаемое описание для списка «История изменений»
    label = Column(String(300), nullable=True)
    # Отменён ли снапшот (undo прошёл) — остаётся в истории как совершённый
    undone = Column(Boolean, nullable=False, default=False)
    # {"fields": ["price", "okpd_code"], "items": [
    #     {"id": 1, "price": 1200.0, "okpd_code": "6109"}, ...]}
    payload = Column(JSON, nullable=False)

    user = relationship("User", backref="bulk_edit_snapshots")
