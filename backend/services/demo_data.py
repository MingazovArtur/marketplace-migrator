"""Демо-аккаунт «попробовать без регистрации».

Общий пользователь `demo` с подложкой товаров и истории операций:
новичок кликает кнопку на форме входа и сразу попадает в рабочий
интерфейс с товарами, историей правок и статистикой — оценивает
продукт до регистрации.

Механика:
- аккаунт один на всех, пароль случайный (войти по паролю нельзя);
- данные сбрасываются раз в сутки (флаг в Redis) или при первом входе,
  если подложка пуста —_demo-товары не «затираются» чужими правками
  дольше 24 часов;
- админ может отключить демо обычной деактивацией пользователя demo
  (get_current_user отклонит токены деактивированного аккаунта).

Сброс никогда не должен ронять вход: любые сбои (Redis недоступен и
т.п.) логируются и обходятся, а не прокидываются наверх.
"""

import logging
import secrets
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from core.auth import get_password_hash
from core.config import settings
from core.time import utcnow
from database.models import (
    BulkEditSnapshot,
    FileOperationLog,
    ImportExportStats,
    Product,
    ProductAttribute,
    ProductVariant,
    User,
)

logger = logging.getLogger(__name__)

DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@marketplace.local"

# Ключ и TTL флага «демо-данные свежие» в Redis
_RESET_KEY = "demo:last_reset"
_RESET_TTL = 24 * 3600


def _photos(seed: str, count: int) -> list[str]:
    """Стабильные демо-фото (picsum: одинаковый seed = однааковая картинка)."""
    return [f"https://picsum.photos/seed/{seed}-{i + 1}/400/400" for i in range(count)]


# ============================================================
# Подложка товаров. Часть полей нарочно пустая (ТН ВЭД, вес,
# габариты) — чтобы были видны сценарии «пропуски → дозаполнение
# дефолтами → миграция». Источники: ozon / wildberries / yandex.
# ============================================================
DEMO_PRODUCTS = [
    {
        "name": "Худи oversize «Basic Cotton»",
        "source": "ozon",
        "category": "Одежда",
        "mapped_category": "Одежда и обувь / Худи и свитшоты",
        "price": 2490.00,
        "brand": "BasicCotton",
        "sku": "BC-HOOD-001",
        "barcode": "4600123456781",
        "description": "Худи oversize из плотного футера (280 г/м2), начёс изнутри.",
        "weight_grams": 520,
        "package_weight_grams": 560,
        "package_width_mm": 350,
        "package_height_mm": 80,
        "package_length_mm": 280,
        "vat_rate": "none",
        "okpd_code": "6109",
        "stock": 42,
        "status": "success",
        "photos": _photos("hoodie", 3),
        "variants": [
            {"sku": "BC-HOOD-001-S", "size": "S", "color": "Серый меланж", "price": 2490.00, "stock": 12},
            {"sku": "BC-HOOD-001-M", "size": "M", "color": "Серый меланж", "price": 2490.00, "stock": 18},
            {"sku": "BC-HOOD-001-L", "size": "L", "color": "Чёрный", "price": 2590.00, "stock": 12},
        ],
        "attributes": [
            {"name": "Материал", "value": "Хлопок 80%, полиэстер 20%"},
            {"name": "Сезон", "value": "Демисезон"},
        ],
    },
    {
        "name": "Футболка однотонная унисекс",
        "source": "wildberries",
        "category": "Одежда",
        "price": 890.00,
        "brand": "BasicCotton",
        "sku": "BC-TEE-002",
        "barcode": "4600123456798",
        "description": "Базовая однотонная футболка, кулирка 100% хлопок.",
        "weight_grams": 180,
        "package_weight_grams": 200,
        "package_width_mm": 280,
        "package_height_mm": 40,
        "package_length_mm": 220,
        "vat_rate": "none",
        "okpd_code": "6109",
        "stock": 130,
        "status": "success",
        "photos": _photos("tshirt", 2),
        "variants": [
            {"sku": "BC-TEE-002-S", "size": "S", "color": "Белый", "price": 890.00, "stock": 40},
            {"sku": "BC-TEE-002-M", "size": "M", "color": "Белый", "price": 890.00, "stock": 50},
            {"sku": "BC-TEE-002-XL", "size": "XL", "color": "Тёмно-синий", "price": 940.00, "stock": 40},
        ],
        "attributes": [{"name": "Материал", "value": "100% хлопок"}],
    },
    {
        "name": "Джинсы mom fit высокой посадки",
        "source": "ozon",
        "category": "Одежда",
        "price": 3990.00,
        "brand": "DenimLab",
        "sku": "DL-JEANS-003",
        # нарочно без okpd_code и габаритов — демо «пропусков»
        "weight_grams": 700,
        "vat_rate": "none",
        "stock": 8,
        "status": "pending",
        "photos": _photos("jeans", 2),
        "attributes": [{"name": "Состав", "value": "98% хлопок, 2% эластан"}],
    },
    {
        "name": "Платье миди трикотажное",
        "source": "yandex",
        "category": "Одежда",
        "mapped_category": "Одежда и обувь / Платья",
        "price": 2790.00,
        "brand": "Aurelia",
        "sku": "AU-DRESS-004",
        "barcode": "4600123456804",
        "weight_grams": 350,
        "package_weight_grams": 380,
        "package_width_mm": 300,
        "package_height_mm": 60,
        "package_length_mm": 240,
        "vat_rate": "none",
        "okpd_code": "6104",
        "stock": 21,
        "status": "success",
        "photos": _photos("dress", 3),
    },
    {
        "name": "Кроссовки беговые AirFlex Runner",
        "source": "ozon",
        "category": "Обувь",
        "mapped_category": "Обувь / Кроссовки",
        "price": 5490.00,
        "brand": "AirFlex",
        "sku": "AF-RUN-005",
        "barcode": "4600987654321",
        "weight_grams": 310,
        "package_weight_grams": 900,
        "package_width_mm": 320,
        "package_height_mm": 160,
        "package_length_mm": 420,
        "vat_rate": "none",
        "okpd_code": "6404",
        "stock": 35,
        "status": "success",
        "photos": _photos("sneakers", 3),
        "variants": [
            {"sku": "AF-RUN-005-41", "size": "41", "color": "Серый", "price": 5490.00, "stock": 10},
            {"sku": "AF-RUN-005-42", "size": "42", "color": "Серый", "price": 5490.00, "stock": 15},
            {"sku": "AF-RUN-005-43", "size": "43", "color": "Чёрный", "price": 5590.00, "stock": 10},
        ],
    },
    {
        "name": "Ботинки зимние кожаные NordicWarm",
        "source": "wildberries",
        "category": "Обувь",
        "price": 7990.00,
        "brand": "NordicWarm",
        "sku": "NW-BOOT-006",
        "barcode": "4600987654338",
        # нарочно без веса/НДС — демо «пропусков»
        "package_weight_grams": 1400,
        "package_width_mm": 340,
        "package_height_mm": 180,
        "package_length_mm": 330,
        "okpd_code": "6403",
        "stock": 6,
        "status": "pending",
        "photos": _photos("boots", 2),
    },
    {
        "name": "Рюкзак городской 18 л CityPack",
        "source": "ozon",
        "category": "Аксессуары",
        "mapped_category": "Аксессуары / Сумки и рюкзаки",
        "price": 2190.00,
        "brand": "CityPack",
        "sku": "CP-BAG-007",
        "barcode": "4600555544441",
        "weight_grams": 450,
        "package_weight_grams": 480,
        "package_width_mm": 300,
        "package_height_mm": 120,
        "package_length_mm": 300,
        "vat_rate": "none",
        "okpd_code": "4202",
        "stock": 54,
        "status": "success",
        "photos": _photos("backpack", 3),
        "attributes": [{"name": "Материал", "value": "Полиэстер, водоотталкивающая пропитка"}],
    },
    {
        "name": "Ремень кожаный классический 35 мм",
        "source": "yandex",
        "category": "Аксессуары",
        "price": 1490.00,
        "brand": "LeatherLine",
        "sku": "LL-BELT-008",
        # нарочно без ТН ВЭД/штрихкода/фото — демо «пропусков»
        "weight_grams": 120,
        "package_weight_grams": 140,
        "package_width_mm": 120,
        "package_height_mm": 40,
        "package_length_mm": 160,
        "vat_rate": "none",
        "stock": 19,
        "status": "pending",
        "photos": [],
    },
    {
        "name": "Смарт-часы PulseFit S2 (черные)",
        "source": "wildberries",
        "category": "Электроника",
        "mapped_category": "Электроника / Смарт-часы",
        "price": 4990.00,
        "brand": "PulseFit",
        "sku": "PF-WATCH-009",
        "barcode": "4600777788889",
        "weight_grams": 210,
        "package_weight_grams": 350,
        "package_width_mm": 120,
        "package_height_mm": 70,
        "package_length_mm": 190,
        "vat_rate": "none",
        "okpd_code": "8517",
        "stock": 27,
        "status": "success",
        "photos": _photos("smartwatch", 2),
        "attributes": [{"name": "Экран", "value": "AMOLED 1.4\""}],
    },
    {
        "name": "Наушники беспроводные TWS AirSound Pro",
        "source": "ozon",
        "category": "Электроника",
        "price": 2990.00,
        "brand": "AirSound",
        "sku": "AS-TWS-010",
        "barcode": "4600777788896",
        "weight_grams": 60,
        "package_weight_grams": 180,
        "package_width_mm": 100,
        "package_height_mm": 50,
        "package_length_mm": 100,
        "vat_rate": "none",
        "okpd_code": "8518",
        "stock": 88,
        "status": "success",
        "photos": _photos("tws", 2),
    },
    {
        "name": "Постельное бельё евро, сатин",
        "source": "wildberries",
        "category": "Дом и сад",
        "price": 3490.00,
        "brand": "DreamHome",
        "sku": "DH-BED-011",
        "barcode": "4600333366663",
        # нарочно без габаритов и веса — демо «пропусков»
        "vat_rate": "none",
        "okpd_code": "6302",
        "stock": 15,
        "status": "pending",
        "photos": _photos("bedding", 2),
    },
    {
        "name": "Плед флисовый 150×200 см",
        "source": "yandex",
        "category": "Дом и сад",
        "mapped_category": "Дом и сад / Текстиль",
        "price": 1590.00,
        "brand": "DreamHome",
        "sku": "DH-PLD-012",
        "barcode": "4600333366670",
        "weight_grams": 850,
        "package_weight_grams": 900,
        "package_width_mm": 400,
        "package_height_mm": 150,
        "package_length_mm": 400,
        # нарочно без ТН ВЭД и НДС — демо «пропусков»
        "stock": 33,
        "status": "success",
        "photos": _photos("plaid", 2),
    },
]

# Краткая история операций (ImportExportStats) за последние 7 дней —
# чтобы дашборд и аналитика в демо не были пустыми.
DEMO_OPERATIONS = [
    # (дней назад, operation, platform, status, total, success, failed, duration_ms)
    (6, "import_file", "ozon", "success", 12, 12, 0, 8400),
    (6, "media_download", "ozon", "success", 12, 11, 1, 41200),
    (5, "migrate", "wildberries", "partial", 6, 5, 1, 15600),
    (4, "export", "wildberries", "success", 5, 5, 0, 3100),
    (3, "edit", None, "success", 4, 4, 0, 900),
    (2, "export", "ozon", "success", 8, 8, 0, 4200),
    (2, "migrate", "yandex", "success", 3, 3, 0, 9800),
    (1, "import_file", "wildberries", "success", 4, 4, 0, 5100),
    (1, "export", "yandex", "error", 0, 0, 0, 700),
    (0, "export", "ozon", "success", 2, 2, 0, 2400),
]


# ============================================================
# Redis-флаг свежести (сбои не роняют вход)
# ============================================================
def _redis():
    try:
        import redis

        return redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2)
    except Exception as e:  # redis не установлен/недоступен
        logger.warning(f"demo: Redis недоступен ({e}) — сброс только по пустой подложке")
        return None


def _reset_flag_fresh() -> bool:
    """True — подложка свежая, сбрасывать не надо."""
    try:
        client = _redis()
        return bool(client and client.exists(_RESET_KEY))
    except Exception:
        return True  # Redis лёг — не сбрасываем (лучше слегка старые данные, чем упавший вход)


def _set_reset_flag() -> None:
    try:
        client = _redis()
        if client:
            client.setex(_RESET_KEY, _RESET_TTL, utcnow().isoformat())
    except Exception as e:
        logger.warning(f"demo: не удалось поставить флаг сброса ({e})")


# ============================================================
# Публичные функции
# ============================================================
def ensure_demo_user(db) -> User:
    """Найти или создать демо-пользователя (пароль случайный — вход только через /demo)."""
    user = db.query(User).filter(User.username == DEMO_USERNAME).first()
    if user:
        return user

    user = User(
        email=DEMO_EMAIL,
        username=DEMO_USERNAME,
        hashed_password=get_password_hash(secrets.token_urlsafe(24)),
        role="user",
        is_active=True,
        email_verified_at=utcnow(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # гонка двух одновременных демо-входов: второй увидит уже созданного
        db.rollback()
        user = db.query(User).filter(User.username == DEMO_USERNAME).first()
        if user is None:
            raise
    db.refresh(user)
    logger.info(f"Создан демо-аккаунт (id={user.id})")
    return user


def reset_demo_if_stale(db, user: User) -> bool:
    """Сбросить демо-данные, если прошло >24 ч или подложка пуста. True — был сброс."""
    products_left = db.query(Product.id).filter(Product.user_id == user.id).count()
    if products_left > 0 and _reset_flag_fresh():
        return False

    _wipe_demo_data(db, user)
    _seed_demo_data(db, user)
    db.commit()
    _set_reset_flag()
    logger.info("Демо-данные пересозданы (12 товаров, история за 7 дней)")
    return True


# ============================================================
# Внутреннее: очистка и подложка
# ============================================================
def _wipe_demo_data(db, user: User) -> None:
    """Полная очистка данных демо-пользователя (варианты/характеристики — явно,
    чтобы работать и в SQLite, где FK-каскады не гарантированы)."""
    product_ids = [row.id for row in db.query(Product.id).filter(Product.user_id == user.id).all()]
    if product_ids:
        db.query(ProductVariant).filter(ProductVariant.product_id.in_(product_ids)).delete(
            synchronize_session=False
        )
        db.query(ProductAttribute).filter(ProductAttribute.product_id.in_(product_ids)).delete(
            synchronize_session=False
        )
        db.query(Product).filter(Product.id.in_(product_ids)).delete(synchronize_session=False)
    db.query(BulkEditSnapshot).filter(BulkEditSnapshot.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(ImportExportStats).filter(ImportExportStats.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(FileOperationLog).filter(FileOperationLog.user_id == user.id).delete(
        synchronize_session=False
    )


def _seed_demo_data(db, user: User) -> None:
    now = utcnow()

    # --- товары + варианты + характеристики ---
    created_ids: list[int] = []
    for spec in DEMO_PRODUCTS:
        photos = spec.get("photos", [])
        product = Product(
            user_id=user.id,
            name=spec["name"],
            source=spec["source"],
            price=spec["price"],
            status=spec.get("status", "pending"),
            description=spec.get("description", ""),
            photos_count=len(photos),
            photos=photos,
            category=spec["category"],
            mapped_category=spec.get("mapped_category"),
            barcode=spec.get("barcode"),
            weight_grams=spec.get("weight_grams"),
            package_weight_grams=spec.get("package_weight_grams"),
            package_width_mm=spec.get("package_width_mm"),
            package_height_mm=spec.get("package_height_mm"),
            package_length_mm=spec.get("package_length_mm"),
            vat_rate=spec.get("vat_rate"),
            okpd_code=spec.get("okpd_code"),
            sku=spec.get("sku"),
            stock=spec.get("stock"),
            brand=spec.get("brand"),
            created_at=now - timedelta(days=7),
        )
        db.add(product)
        db.flush()  # нужен id для вариантов/характеристик
        created_ids.append(product.id)

        for order, variant in enumerate(spec.get("variants", [])):
            db.add(
                ProductVariant(
                    product_id=product.id,
                    sku=variant["sku"],
                    size=variant.get("size"),
                    color=variant.get("color"),
                    price=variant["price"],
                    stock=variant.get("stock"),
                    sort_order=order,
                )
            )
        for order, attribute in enumerate(spec.get("attributes", [])):
            db.add(
                ProductAttribute(
                    product_id=product.id,
                    name=attribute["name"],
                    value=attribute["value"],
                    sort_order=order,
                )
            )

    # --- история операций для дашборда/аналитики ---
    for days_ago, operation, platform, stat, total, success, failed, duration in DEMO_OPERATIONS:
        db.add(
            ImportExportStats(
                user_id=user.id,
                operation=operation,
                platform=platform,
                status=stat,
                total_items=total,
                success_items=success,
                failed_items=failed,
                duration_ms=duration,
                created_at=now - timedelta(days=days_ago, minutes=37),
            )
        )

    # --- пара записей в истории операций (страница «История») ---
    db.add(
        FileOperationLog(
            user_id=user.id,
            operation="import_file",
            platform="ozon",
            filename="ozon_Одежда_Худи.xlsx",
            mode="create",
            status="success",
            total_rows=12,
            imported=12,
            updated=0,
            failed=0,
        )
    )
    db.add(
        FileOperationLog(
            user_id=user.id,
            operation="export",
            platform="wildberries",
            filename="export_wb_2026-11-16.xlsx",
            mode="create",
            status="success",
            total_rows=5,
            imported=5,
            updated=0,
            failed=0,
        )
    )

    # --- пара снапшотов правок (аналитика: «история изменений») ---
    if len(created_ids) >= 4:
        db.add(
            BulkEditSnapshot(
                user_id=user.id,
                action="bulk_update",
                label="Массовое обновление: цена +10% (3 товара)",
                created_at=now - timedelta(days=3),
                payload={
                    "fields": ["price"],
                    "items": [
                        {"id": created_ids[i], "price": 1990.00} for i in range(3)
                    ],
                },
            )
        )
        db.add(
            BulkEditSnapshot(
                user_id=user.id,
                action="tnved",
                label="Массовый подбор ТН ВЭД (проверка)",
                created_at=now - timedelta(days=1),
                payload={
                    "fields": ["okpd_code"],
                    "items": [{"id": created_ids[3], "okpd_code": "6104"}],
                },
            )
        )
