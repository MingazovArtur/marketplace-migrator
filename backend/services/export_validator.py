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
    "yandex": {"name_max": 255, "desc_max": 500, "photos_min": 1, "photos_max": 10},
    "magnit": {"name_max": 255, "desc_max": 500, "photos_min": 1, "photos_max": 10},
}


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
    price = product.get("price") or 0
    if price <= 0:
        issues.append({"field": "price", "level": "error", "message": "Цена не задана (0 ₽)"})

    # Фото
    photos = product.get("photos") or []
    if len(photos) < rules["photos_min"]:
        issues.append({"field": "photos", "level": "warning", "message": "Нет ни одного фото"})
    elif len(photos) > rules["photos_max"]:
        issues.append(
            {
                "field": "photos",
                "level": "warning",
                "message": f"Фото {len(photos)} (лимит {rules['photos_max']}) — лишние отброшены",
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
