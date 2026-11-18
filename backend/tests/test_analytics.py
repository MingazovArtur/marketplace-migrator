"""Тесты аналитики (services/analytics.py) — чистые функции, без БД."""

from services.analytics import compute_categories, compute_fill


def _product(**overrides):
    """Полностью заполненный товар; переопределения ломают нужные поля."""
    base = {
        "id": 1,
        "name": "Товар",
        "price": 100.0,
        "brand": "Brand",
        "category": "Одежда",
        "mapped_category": "Одежда / Футболки",
        "barcode": "4600000000000",
        "weight_grams": 200,
        "package_weight_grams": 250,
        "package_width_mm": 300,
        "package_height_mm": 50,
        "package_length_mm": 250,
        "vat_rate": "none",
        "okpd_code": "6109",
        "sku": "SKU-1",
        "stock": 10,
        "photos_count": 2,
        "description": "Описание",
    }
    base.update(overrides)
    return base


def test_fill_empty_products():
    data = compute_fill([])
    assert data["total"] == 0
    assert data["ready_count"] == 0
    assert data["avg_fill_pct"] == 0.0
    assert all(f["pct"] == 0.0 for f in data["fields"])


def test_fill_full_product_is_ready():
    data = compute_fill([_product()])
    assert data["total"] == 1
    assert data["ready_count"] == 1
    assert data["ready_pct"] == 100.0
    assert data["avg_fill_pct"] == 100.0
    for f in data["fields"]:
        assert f["filled"] == 1, f"поле {f['key']} должно быть заполнено"


def test_fill_counts_gaps_per_field():
    products = [
        _product(),
        _product(okpd_code=None),  # нет ТН ВЭД
        _product(okpd_code=None, vat_rate=None),  # нет ТН ВЭД и НДС
    ]
    data = compute_fill(products)

    by_key = {f["key"]: f for f in data["fields"]}
    assert by_key["okpd_code"]["filled"] == 1
    assert by_key["okpd_code"]["pct"] == 33.3
    assert by_key["vat_rate"]["filled"] == 2
    assert by_key["vat_rate"]["pct"] == 66.7
    # товар готов, только если заполнены ВСЕ критические поля
    assert data["ready_count"] == 1


def test_price_zero_counts_as_gap():
    data = compute_fill([_product(price=0)])
    by_key = {f["key"]: f for f in data["fields"]}
    assert by_key["price"]["filled"] == 0
    assert data["ready_count"] == 0


def test_default_category_counts_as_gap():
    data = compute_fill([_product(category="Не указана")])
    by_key = {f["key"]: f for f in data["fields"]}
    assert by_key["category"]["filled"] == 0


def test_critical_fields_marked():
    data = compute_fill([])
    by_key = {f["key"]: f for f in data["fields"]}
    assert by_key["okpd_code"]["critical"] is True
    assert by_key["brand"]["critical"] is True
    assert by_key["barcode"]["critical"] is False
    assert by_key["photos"]["critical"] is False


def test_categories_grouping_and_sort():
    products = [
        _product(category="Одежда", price=100.0),
        _product(category="Одежда", price=200.0),
        _product(category="Обувь", price=900.0, mapped_category=None),
    ]
    rows = compute_categories(products)
    assert rows[0]["category"] == "Одежда"  # сортировка по количеству
    assert rows[0]["count"] == 2
    assert rows[0]["avg_price"] == 150.0
    assert rows[1]["category"] == "Обувь"
    assert rows[1]["mapped_pct"] == 0.0
    assert rows[0]["mapped_pct"] == 100.0


def test_categories_limit():
    products = [_product(category=f"Категория {i}") for i in range(15)]
    rows = compute_categories(products, limit=10)
    assert len(rows) == 10
