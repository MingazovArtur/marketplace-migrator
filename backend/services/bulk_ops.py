"""
Чистые функции массового обновления товаров: предпросмотр и undo-снапшот.

Вынесены из роутера, чтобы покрыть тестами без БД (см. tests/test_bulk_ops.py).

Работают с "простыми" товароподобными объектами: достаточно атрибутов
id, name, price, brand, mapped_category (ORM-модель Product подходит).
"""

from __future__ import annotations

from typing import Any

# Ограничения повторяют валидацию в bulk-update на конце пользователя:
# наценка -100% обнуляет цену (недопустимо), фикс-цена должна быть > 0.
MIN_PRICE_PERCENT = -99.99  # softer guard; жёсткую проверку делает роутер
MAX_PRICE_PERCENT = 10_000


def _new_price(base: float, price: float | None, price_percent: float | None) -> float | None:
    """Новая цена товара по правилам bulk-update: фикс-цена ИЛИ процент от текущей."""
    if price is not None:
        return round(float(price), 2)
    if price_percent is not None:
        return round(base * (1 + float(price_percent) / 100), 2)
    return None


def compute_preview(
    products: list[Any],
    price: float | None = None,
    price_percent: float | None = None,
    sample_limit: int = 3,
) -> dict:
    """
    Предпросмотр массового обновления БЕЗ записи в БД.

    Возвращает:
        {
          "count": int,                 # товаров затронуто
          "prices_changed": bool,       # меняется ли цена
          "price_min"/"price_max"/"price_avg": float | None,  # НОВЫЕ цены
          "sample": [{id, name, old_price, new_price}],        # первые sample_limit
          "invalid_prices": int,        # товаров с нулевой/пустой базовой ценой
        }
    """
    items = list(products)
    count = len(items)
    changes_price = price is not None or price_percent is not None

    new_prices: list[float] = []
    sample: list[dict] = []
    invalid_prices = 0

    for p in items:
        base = float(p.price or 0)
        new_p = _new_price(base, price, price_percent) if changes_price else None
        if changes_price:
            if base <= 0:
                invalid_prices += 1
                continue
            new_prices.append(new_p)
            if len(sample) < sample_limit:
                sample.append(
                    {
                        "id": p.id,
                        "name": p.name,
                        "old_price": round(base, 2),
                        "new_price": new_p,
                    }
                )

    return {
        "count": count,
        "prices_changed": changes_price,
        "price_min": round(min(new_prices), 2) if new_prices else None,
        "price_max": round(max(new_prices), 2) if new_prices else None,
        "price_avg": round(sum(new_prices) / len(new_prices), 2) if new_prices else None,
        "sample": sample,
        "invalid_prices": invalid_prices,
    }


def build_snapshot_payload(products: list[Any], fields: list[str]) -> dict:
    """
    Снапшот ТЕКУЩИХ значений перед изменением (для undo).

    Decimal из ORM конвертируем в float — JSON не умеет Decimal.
    """
    items = []
    for p in products:
        items.append(
            {
                "id": p.id,
                "price": float(p.price) if p.price is not None else None,
                "brand": p.brand,
                "mapped_category": p.mapped_category,
            }
        )
    return {"fields": list(fields), "items": items}


def apply_snapshot(products_by_id: dict[int, Any], snapshot: dict) -> dict:
    """
    Восстановление значений из снапшота (undo).

    Товары, удалённые после снапшота, пропускаются (по ним не падаем).
    Возвращает {"restored": N, "skipped_missing": M}.
    """
    restored = 0
    skipped = 0
    for item in snapshot.get("items", []):
        p = products_by_id.get(item.get("id"))
        if p is None:
            skipped += 1
            continue
        price = item.get("price")
        p.price = price if price is not None else None
        p.brand = item.get("brand")
        p.mapped_category = item.get("mapped_category")
        restored += 1
    return {"restored": restored, "skipped_missing": skipped}


def escape_like(q: str) -> str:
    """Экранирование %, _ и \\ для SQL ILIKE-поиска по пользовательскому вводу."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def parse_float_or_none(value: str | float | int | None) -> float | None:
    """Безопасный парсинг числа из формы: '' / мусор / None -> None."""
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
