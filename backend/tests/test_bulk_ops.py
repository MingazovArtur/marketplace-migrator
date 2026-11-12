"""
Тесты чистых функций массового обновления: предпросмотр и undo-снапшот.
См. services/bulk_ops.py — функции без БД, тестируются напрямую.
"""

import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.bulk_ops import (  # noqa: E402
    apply_snapshot,
    build_snapshot_payload,
    compute_preview,
    escape_like,
    parse_float_or_none,
)


class FakeProduct:
    """Товароподобный объект: достаточно id/name/price/brand/mapped_category."""

    def __init__(self, id, name, price, brand=None, mapped_category=None, okpd_code=None, vat_rate=None):  # noqa: A002
        self.id = id
        self.name = name
        self.price = price
        self.brand = brand
        self.mapped_category = mapped_category
        self.okpd_code = okpd_code
        self.vat_rate = vat_rate


PRODUCTS = [
    FakeProduct(1, "Футболка", Decimal("1000.00"), brand="OldBrand", mapped_category="А / Б", okpd_code="6109"),
    FakeProduct(2, "Кроссовки", Decimal("2000.00"), brand=None, mapped_category=None, okpd_code=None),
    FakeProduct(3, "Носки", Decimal("0"), brand="X", mapped_category=None, okpd_code="6115"),
]


# ==================== compute_preview ====================

def test_preview_percent_min_max_avg():
    p = compute_preview(PRODUCTS[:2], price_percent=15)
    # 1000 -> 1150, 2000 -> 2300
    assert p["count"] == 2
    assert p["prices_changed"] is True
    assert p["price_min"] == 1150.0
    assert p["price_max"] == 2300.0
    assert p["price_avg"] == 1725.0
    assert p["invalid_prices"] == 0


def test_preview_percent_negative_discount():
    p = compute_preview([PRODUCTS[0]], price_percent=-10)
    assert p["price_min"] == 900.0
    assert p["price_max"] == 900.0


def test_preview_fixed_price():
    p = compute_preview(PRODUCTS[:2], price=990)
    assert p["price_min"] == 990.0
    assert p["price_max"] == 990.0
    assert p["price_avg"] == 990.0


def test_preview_skips_zero_price_products():
    # товар с ценой 0 не участвует в стат-ке новых цен
    p = compute_preview(PRODUCTS, price_percent=50)
    assert p["count"] == 3
    assert p["invalid_prices"] == 1
    assert p["price_min"] == 1500.0  # 1000 -> 1500
    assert p["price_max"] == 3000.0


def test_preview_rounding_two_decimals():
    p = compute_preview([FakeProduct(1, "x", Decimal("999.99"))], price_percent=10)
    assert p["price_min"] == 1099.99


def test_preview_sample_capped_and_sorted():
    many = [FakeProduct(i, f"т{i}", Decimal("100")) for i in range(10)]
    p = compute_preview(many, price_percent=5)
    assert len(p["sample"]) == 3
    assert p["sample"][0] == {"id": 0, "name": "т0", "old_price": 100.0, "new_price": 105.0}


def test_preview_without_price_change():
    p = compute_preview(PRODUCTS)  # только бренд/категория
    assert p["prices_changed"] is False
    assert p["price_min"] is None
    assert p["price_max"] is None
    assert p["price_avg"] is None
    assert p["sample"] == []
    assert p["count"] == 3


def test_preview_empty_products():
    p = compute_preview([], price_percent=15)
    assert p["count"] == 0
    assert p["price_min"] is None


# ==================== build_snapshot_payload ====================

def test_snapshot_payload_decimal_to_float():
    snap = build_snapshot_payload(PRODUCTS, ["price", "brand", "category"])
    # ✅ v4: alias "category" -> колонка "mapped_category"
    assert snap["fields"] == ["price", "brand", "mapped_category"]
    items = {i["id"]: i for i in snap["items"]}
    assert items[1]["price"] == 1000.0  # Decimal -> float (JSON-сериализуемо)
    assert items[1]["brand"] == "OldBrand"
    assert items[1]["mapped_category"] == "А / Б"
    assert items[2]["brand"] is None
    # JSON-сериализуемость целиком
    import json

    json.dumps(snap)


def test_snapshot_payload_only_listed_fields():
    """v4: снапшот хранит РОВНО перечисленные поля (например, только ТН ВЭД)."""
    snap = build_snapshot_payload(PRODUCTS, ["okpd_code"])
    assert snap["fields"] == ["okpd_code"]
    items = {i["id"]: i for i in snap["items"]}
    assert items[1] == {"id": 1, "okpd_code": "6109"}
    assert "price" not in items[1]


def test_snapshot_payload_skips_unknown_fields():
    """v4: price_percent и прочие не-колонки в снапшот не попадают."""
    snap = build_snapshot_payload(PRODUCTS, ["price", "price_percent", "nosuchfield"])
    assert snap["fields"] == ["price"]


# ==================== apply_snapshot ====================

def test_apply_snapshot_restores_values():
    snap = build_snapshot_payload(PRODUCTS, ["price", "brand", "category"])
    # меняем товары (как это делает bulk_update)
    PRODUCTS[0].price = Decimal("1150.00")
    PRODUCTS[0].brand = "NewBrand"
    PRODUCTS[1].mapped_category = "Новая категория"

    result = apply_snapshot({p.id: p for p in PRODUCTS}, snap)
    assert result["restored"] == 3
    assert result["skipped_missing"] == 0
    assert result["fields"] == ["price", "brand", "mapped_category"]
    assert PRODUCTS[0].price == 1000.0
    assert PRODUCTS[0].brand == "OldBrand"
    assert PRODUCTS[1].mapped_category is None


def test_apply_snapshot_only_listed_fields_touched():
    """v4: undo восстанавливает ТОЛЬКО поля из снапшота, остальное не трогает."""
    snap = build_snapshot_payload(PRODUCTS, ["okpd_code"])
    PRODUCTS[0].okpd_code = "9999"
    PRODUCTS[0].brand = "ChangedButNotInSnapshot"
    before_price = PRODUCTS[0].price

    result = apply_snapshot({p.id: p for p in PRODUCTS}, snap)
    assert result["restored"] == 3
    assert PRODUCTS[0].okpd_code == "6109"
    assert PRODUCTS[0].brand == "ChangedButNotInSnapshot"  # НЕ откачено
    assert PRODUCTS[0].price == before_price  # НЕ откачено


def test_apply_snapshot_legacy_format_without_fields():
    """v4: легаси-снапшоты (без fields) восстанавливают цену/бренд/категорию."""
    legacy = {
        "items": [
            {"id": 1, "price": 1000.0, "brand": "OldBrand", "mapped_category": "А / Б"},
            {"id": 2, "price": 2000.0, "brand": None, "mapped_category": None},
        ]
    }
    PRODUCTS[0].price = Decimal("777")
    PRODUCTS[0].brand = "Wrong"

    result = apply_snapshot({p.id: p for p in PRODUCTS}, legacy)
    assert result["restored"] == 2
    assert PRODUCTS[0].price == 1000.0
    assert PRODUCTS[0].brand == "OldBrand"


def test_apply_snapshot_skips_deleted_products():
    snap = build_snapshot_payload(PRODUCTS[:3], ["brand"])
    # товар 2 «удалён» — его нет в products_by_id
    result = apply_snapshot({p.id: p for p in PRODUCTS if p.id != 2}, snap)
    assert result["restored"] == 2
    assert result["skipped_missing"] == 1


def test_apply_snapshot_empty_items():
    result = apply_snapshot({}, {"fields": [], "items": []})
    assert result["restored"] == 0
    assert result["skipped_missing"] == 0


# ==================== escape_like / parse ====================

def test_escape_like_wildcards():
    assert escape_like("100%_x\\") == "100\\%\\_x\\\\"


def test_parse_float_or_none():
    assert parse_float_or_none("") is None
    assert parse_float_or_none(None) is None
    assert parse_float_or_none("abc") is None
    assert parse_float_or_none("15") == 15.0
    assert parse_float_or_none("15,5") == 15.5
    assert parse_float_or_none(-10) == -10.0
