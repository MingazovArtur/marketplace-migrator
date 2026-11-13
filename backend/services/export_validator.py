"""
Валидатор товаров перед выгрузкой в формат площадок.
Проверяет карточки на соответствие требованиям личных кабинетов маркетплейсов.
"""

import logging

logger = logging.getLogger(__name__)

# Требования площадок к полям карточки
VALIDATION_RULES = {
    "wildberries": {"name_max": 100, "desc_max": 1000, "photos_min": 1, "photos_max": 30},
    "ozon": {"name_max": 255, "desc_max": 3000, "photos_min": 1, "photos_max": 15},
    "yandex": {"name_max": 255, "desc_max": 6000, "photos_min": 1, "photos_max": 30},
    "magnit": {"name_max": 255, "desc_max": 500, "photos_min": 1, "photos_max": 10},
    "megamarket": {"name_max": 200, "desc_max": 3000, "photos_min": 1, "photos_max": 10},
    "holodilnik": {"name_max": 255, "desc_max": 3000, "photos_min": 1, "photos_max": 10},
    "aliexpress": {"name_max": 255, "desc_max": 5000, "photos_min": 1, "photos_max": 15},
}

FORBIDDEN_PHOTO_HOSTS = ("disk.yandex.", "yadi.sk", "drive.google.", "dropbox.com")


def validate_product(product: dict, platform: str) -> list[dict]:
    """Возвращает список проблем карточки: [{field, level: error|warning, message}]."""
    rules = VALIDATION_RULES.get(platform, VALIDATION_RULES["ozon"])
    issues = []

    # Название
    name = (product.get("name") or "").strip()
    if not name:
        issues.append({"field": "name", "level": "error", "message": "Пустое название товара"})
    elif len(name) > rules["name_max"]:
        issues.append(
            {
                "field": "name",
                "level": "warning",
                "message": f"Название {len(name)} симв. (лимит {rules['name_max']}) — будет обрезано",
            }
        )

    # Цена
    price = float(product.get("price") or 0)
    if price <= 0:
        issues.append({"field": "price", "level": "error", "message": "Цена не задана (0 ₽)"})

    # Фото
    photos = [str(u).strip() for u in (product.get("photos") or []) if str(u).strip()]
    if len(photos) < rules["photos_min"]:
        # Для Мегамаркета и AliExpress отсутствие главного фото блокирует загрузку шаблона
        lvl = "error" if platform in ("megamarket", "aliexpress") else "warning"
        issues.append(
            {
                "field": "photos",
                "level": lvl,
                "message": "Не указан URL основного фото"
                if lvl == "error"
                else "Нет ни одного фото",
            }
        )
    elif len(photos) > rules["photos_max"]:
        issues.append(
            {
                "field": "photos",
                "level": "warning",
                "message": f"Фото {len(photos)} (лимит {rules['photos_max']}) — лишние отброшены",
            }
        )

    # Проверка запрещённых облачных ссылок для Мегамаркета и AliExpress
    if photos and platform in ("megamarket", "aliexpress"):
        bad_urls = [
            u
            for u in photos
            if any(host in u.lower() for host in FORBIDDEN_PHOTO_HOSTS)
            or (platform == "aliexpress" and "cloud.mail.ru" in u.lower())
        ]
        if bad_urls:
            issues.append(
                {
                    "field": "photos",
                    "level": "warning",
                    "message": (
                        f"Ссылки на закрытые облачные хранилища (Яндекс.Диск / Google Drive / Dropbox) "
                        f"отклоняются площадкой {platform}. Используйте прямые HTTPS-ссылки на .jpg/.png."
                    ),
                }
            )

    # Специфичные проверки Мегамаркета по документации
    if platform == "megamarket":
        sku = str(product.get("sku") or product.get("external_id") or "")
        if "#" in sku or "%" in sku:
            issues.append(
                {
                    "field": "sku",
                    "level": "warning",
                    "message": "В «Коде товара продавца» Мегамаркета запрещены символы # и % (будут очищены автоматически)",
                }
            )
        barcode = str(product.get("barcode") or "").strip()
        if barcode.startswith("2"):
            issues.append(
                {
                    "field": "barcode",
                    "level": "warning",
                    "message": "Штрихкод начинается с «2» (внутренний) — Мегамаркет требует GTIN (префикс 460–469) или запрос штрихкода в ЛК",
                }
            )

    # Специфичные проверки AliExpress по документации
    if platform == "aliexpress":
        sku = str(product.get("sku") or product.get("external_id") or "")
        if len(sku) > 50:
            issues.append(
                {
                    "field": "sku",
                    "level": "warning",
                    "message": "Артикул (seller SKU ID) длиннее 50 символов — будет обрезан до 50 знаков",
                }
            )
        wg = product.get("package_weight_grams") or product.get("weight_grams") or 0
        if float(wg) <= 0:
            issues.append(
                {
                    "field": "weight",
                    "level": "warning",
                    "message": "Вес не указан — для AliExpress вес и габариты не могут быть равны 0 (будет подставлен дефолт)",
                }
            )

    # Описание
    if not (product.get("description") or "").strip():
        issues.append({"field": "description", "level": "warning", "message": "Пустое описание"})

    # Категория
    if not (product.get("mapped_category") or product.get("category")):
        issues.append({"field": "category", "level": "warning", "message": "Категория не указана"})

    return issues


def has_errors(issues: list[dict]) -> bool:
    return any(i["level"] == "error" for i in issues)


def validate_products(products: list[dict], platform: str) -> dict:
    """Сводка валидации: сколько готово / с предупреждениями / с ошибками."""
    issues_by_product = []
    ready = with_warnings = with_errors = 0

    for p in products:
        issues = validate_product(p, platform)
        levels = {i["level"] for i in issues}
        if "error" in levels:
            with_errors += 1
        elif issues:
            with_warnings += 1
        else:
            ready += 1
        if issues:
            issues_by_product.append(
                {
                    "product_id": p.get("id"),
                    "name": (p.get("name") or "")[:60],
                    "issues": issues,
                }
            )

    return {
        "total": len(products),
        "ready": ready,
        "with_warnings": with_warnings,
        "with_errors": with_errors,
        "issues": issues_by_product[:50],
    }
