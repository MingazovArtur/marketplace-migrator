"""Точки входа валидатора: один товар и список товаров с агрегатами.

Вынесено без изменений из монолита services/spec_validator.py (Р12).

Возвращает список Issue с severity:
  - error: блокирует экспорт (площадка точно отклонит)
  - warning: потенциальная проблема или авто-исправимо при генерации
"""

from collections import Counter

from services.spec_validator._attributes import _validate_attributes
from services.spec_validator._canon import OZON_TEMPLATE_REQUIRED_ORDER
from services.spec_validator._ozon_base import _validate_ozon_base

# Подакцизные товары (из официальной документации Ozon)
EXCISABLE_CATEGORIES = {
    "сахаросодержащие напитки",
    "моторные масла",
    "безалкогольное пиво",
}


# ==================== Точка входа: один товар ====================


def validate_product_by_spec(
    product: dict, spec: dict | None, platform: str = "ozon"
) -> list[dict]:
    """
    Валидирует товар по спеку категории.
    Возвращает список проблем: [{"field": str, "message": str, "severity": "error"|"warning"}]
    """
    issues = []

    # Базовые колонки шаблона площадки
    if platform == "ozon":
        _validate_ozon_base(product, issues)

    # Подакцизные товары
    category = (product.get("mapped_category") or product.get("category") or "").lower()
    if any(exc_cat in category for exc_cat in EXCISABLE_CATEGORIES):
        issues.append(
            {
                "field": "excisable",
                "message": "Подакцизный товар — проверьте требования площадки по маркировке",
                "severity": "warning",
            }
        )

    # Атрибуты категории из спека
    if not spec:
        issues.append(
            {
                "field": "spec",
                "message": "Спека категории нет — загрузите через «Спецификации»",
                "severity": "warning",
            }
        )
        return issues

    _validate_attributes(product, spec, issues)
    return issues


# ==================== Точка входа: список товаров ====================


def validate_products_by_specs(
    products: list, specs_by_category: dict, platform: str = "ozon"
) -> dict:
    """
    Валидирует список товаров по спекам.
    Возвращает:
      {
        "total": int,
        "ready": int,                       # без ошибок
        "ready_with_warnings": int,         # без ошибок, но с предупреждениями
        "errors": int,                      # всего error-issues
        "warnings": int,                    # всего warning-issues
        "products_with_errors": int,        # сколько товаров имеют хотя бы 1 error
        "products_with_warnings": int,      # сколько товаров имеют хотя бы 1 warning
        "duplicate_articles": list[str],
        "template_required": list[str],     # канонические 13 полей шаблона (для фронта)
        "issues": list,
      }
    """
    all_issues = []

    # Проверка дублей артикулов (генератор присвоит _2, _3)
    article_counter = Counter()
    for p in products:
        art = p.get("sku") or p.get("external_id") or f"ID{p.get('id')}"
        article_counter[art] += 1
    duplicate_articles = sorted(a for a, c in article_counter.items() if c > 1)

    for product in products:
        category = product.get("mapped_category") or product.get("category") or "Без категории"
        spec = specs_by_category.get(category)
        issues = validate_product_by_spec(product, spec, platform)

        # Предупредить о дубле артикула
        art = product.get("sku") or product.get("external_id") or f"ID{product.get('id')}"
        if art in duplicate_articles:
            issues.append(
                {
                    "field": "article",
                    "message": f"Артикул «{art}» дублируется — при генерации дубли получат "
                    f"суффиксы _2, _3 (правило Ozon: уникальный артикул на строку)",
                    "severity": "warning",
                }
            )

        if issues:
            all_issues.append(
                {
                    "product_id": product.get("id"),
                    "product_name": product.get("name"),
                    "category": category,
                    "issues": issues,
                }
            )

    errors = sum(sum(1 for i in item["issues"] if i["severity"] == "error") for item in all_issues)
    warnings = sum(
        sum(1 for i in item["issues"] if i["severity"] == "warning") for item in all_issues
    )
    products_with_errors = sum(
        1 for item in all_issues if any(i["severity"] == "error" for i in item["issues"])
    )
    products_with_warnings = sum(
        1 for item in all_issues if any(i["severity"] == "warning" for i in item["issues"])
    )

    # ready_with_warnings: без error, но есть хотя бы 1 warning
    products_only_warnings = sum(
        1
        for item in all_issues
        if not any(i["severity"] == "error" for i in item["issues"])
        and any(i["severity"] == "warning" for i in item["issues"])
    )

    return {
        "total": len(products),
        "ready": len(products) - products_with_errors,
        "ready_with_warnings": products_only_warnings,
        "errors": errors,
        "warnings": warnings,
        "products_with_errors": products_with_errors,
        "products_with_warnings": products_with_warnings,
        "duplicate_articles": duplicate_articles[:20],
        "template_required": OZON_TEMPLATE_REQUIRED_ORDER if platform == "ozon" else [],
        "issues": all_issues,
    }
