"""Тесты демо-подложки (services/demo_data.py) — без БД/Redis.

Проверяем инварианты данных: уникальность, валидность цен, наличие
«пропусков» (ради них подложка и существует) и структуру вариантов.
"""

from services.demo_data import DEMO_PRODUCTS


def test_demo_products_have_required_fields():
    required = {"name", "source", "category", "price", "status"}
    for spec in DEMO_PRODUCTS:
        for field in required:
            assert field in spec, f"у «{spec.get('name')}» нет поля {field}"
            assert spec[field], f"у «{spec['name']}» пустое поле {field}"


def test_demo_products_unique():
    names = [p["name"] for p in DEMO_PRODUCTS]
    assert len(names) == len(set(names)), "имена демо-товаров должны быть уникальны"

    skus = [p["sku"] for p in DEMO_PRODUCTS if p.get("sku")]
    assert len(skus) == len(set(skus)), "SKU демо-товаров должны быть уникальны"


def test_demo_products_prices_positive():
    for spec in DEMO_PRODUCTS:
        assert spec["price"] > 0, f"у «{spec['name']}» цена должна быть > 0"


def test_demo_sources_are_known_platforms():
    allowed_sources = {"ozon", "wildberries", "yandex"}
    for spec in DEMO_PRODUCTS:
        assert spec["source"] in allowed_sources


def test_demo_has_gaps_to_show_fill_flow():
    """Часть товаров нарочно с пропусками — иначе в демо нечего дозаполнять."""
    without_okpd = [p for p in DEMO_PRODUCTS if not p.get("okpd_code")]
    without_vat = [p for p in DEMO_PRODUCTS if not p.get("vat_rate")]
    without_dims = [p for p in DEMO_PRODUCTS if not p.get("package_width_mm")]

    assert len(without_okpd) >= 2, "нужны товары без ТН ВЭД (демо дозаполнения)"
    assert len(without_vat) >= 2, "нужны товары без НДС (демо дозаполнения)"
    assert len(without_dims) >= 2, "нужны товары без габаритов (демо дозаполнения)"


def test_demo_variants_structure():
    for spec in DEMO_PRODUCTS:
        for variant in spec.get("variants", []):
            assert variant.get("sku"), f"у варианта «{spec['name']}» нет SKU"
            assert variant.get("price", 0) > 0


def test_demo_photos_urls_wellformed():
    for spec in DEMO_PRODUCTS:
        photos = spec.get("photos", [])
        assert len(photos) == spec.get("photos_count", len(photos)) or "photos_count" not in spec
        for url in photos:
            assert url.startswith("https://"), "демо-фото должны быть https"
