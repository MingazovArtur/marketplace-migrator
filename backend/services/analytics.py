"""Аналитика селлера: заполненность полей и срезы по категориям.

Вычисления вынесены в чистые функции (без БД) — их тестирует pytest
без окружения: роутер только готовит словари строк из БД.
"""

from statistics import mean

# (key, label, getter, critical). critical — поля, без которых экспорт
# на площадки невозможен (чек-лист выгрузки): незаполненное критическое
# поле = товар не готов к миграции.
FILL_FIELDS = [
    ("brand", "Бренд", lambda p: p.get("brand"), True),
    (
        "category",
        "Категория",
        lambda p: p.get("category") and p.get("category") != "Не указана",
        True,
    ),
    ("price", "Цена", lambda p: p.get("price") is not None and float(p["price"]) > 0, True),
    ("weight_grams", "Вес товара", lambda p: p.get("weight_grams"), True),
    (
        "package_dims",
        "Габариты упаковки",
        lambda p: p.get("package_width_mm") and p.get("package_height_mm") and p.get("package_length_mm"),
        True,
    ),
    ("package_weight_grams", "Вес с упаковкой", lambda p: p.get("package_weight_grams"), True),
    ("vat_rate", "НДС", lambda p: p.get("vat_rate"), True),
    ("okpd_code", "ТН ВЭД", lambda p: p.get("okpd_code"), True),
    ("barcode", "Штрихкод", lambda p: p.get("barcode"), False),
    ("photos", "Фото", lambda p: p.get("photos_count"), False),
    ("sku", "Артикул (SKU)", lambda p: p.get("sku"), False),
    ("stock", "Остаток", lambda p: p.get("stock") is not None, False),
    ("description", "Описание", lambda p: p.get("description"), False),
]

_CRITICAL = [(k, g) for k, _, g, crit in FILL_FIELDS if crit]


def _product_fill_pct(product: dict) -> float:
    if not FILL_FIELDS:
        return 0.0
    filled = sum(1 for _, _, getter, _ in FILL_FIELDS if getter(product))
    return filled / len(FILL_FIELDS) * 100


def _is_ready(product: dict) -> bool:
    """Все критические поля заполнены — товар можно выгружать на площадку."""
    return all(getter(product) for _, getter in _CRITICAL)


def compute_fill(products: list[dict]) -> dict:
    """Заполненность полей по всем товарам пользователя."""
    total = len(products)
    fields = []
    for key, label, getter, critical in FILL_FIELDS:
        filled = sum(1 for p in products if getter(p))
        fields.append(
            {
                "key": key,
                "label": label,
                "filled": filled,
                "pct": round(filled / total * 100, 1) if total else 0.0,
                "critical": critical,
            }
        )

    avg_fill_pct = round(mean(_product_fill_pct(p) for p in products), 1) if products else 0.0
    ready_count = sum(1 for p in products if _is_ready(p))
    return {
        "total": total,
        "fields": fields,
        "avg_fill_pct": avg_fill_pct,
        "ready_count": ready_count,
        "ready_pct": round(ready_count / total * 100, 1) if total else 0.0,
    }


def compute_categories(products: list[dict], limit: int = 10) -> list[dict]:
    """Срез по категориям: количество, средняя цена, заполненность, маппинг."""
    groups: dict[str, list[dict]] = {}
    for p in products:
        category = p.get("category") or "Не указана"
        groups.setdefault(category, []).append(p)

    rows = []
    for category, items in groups.items():
        prices = [float(p["price"]) for p in items if p.get("price") is not None]
        rows.append(
            {
                "category": category,
                "count": len(items),
                "avg_price": round(mean(prices), 2) if prices else 0.0,
                "avg_fill_pct": round(mean(_product_fill_pct(p) for p in items), 1),
                "mapped_pct": round(
                    sum(1 for p in items if p.get("mapped_category")) / len(items) * 100, 1
                ),
                "ready_count": sum(1 for p in items if _is_ready(p)),
            }
        )

    rows.sort(key=lambda r: -r["count"])
    return rows[:limit]
