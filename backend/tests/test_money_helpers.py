"""Тесты денежных значений (P-1, неделя 3) и чистых хелперов генерации XLSX / миграций."""

from decimal import Decimal

from database.models import Product, ProductVariant
from database.repository.products import ProductRepository
from services.xlsx_generator.common import _generate_ean13, _norm, _slug, _strip_html
from tasks.matching import _base_source, _safe_float, _stem_ru

# ---------------------------------------------------------------------------
# P-1: Numeric-колонки отдают Decimal — наружу (JSON/openpyxl) отдаём float
# ---------------------------------------------------------------------------


def _make_product(**overrides):
    base = {
        "id": 1,
        "user_id": 7,
        "name": "Футболка",
        "source": "Магнит Маркет (Файл)",
        "price": Decimal("1999.99"),
        "status": "pending",
        "photos": [],
        "sku_count": 1,
    }
    base.update(overrides)
    return Product(**base)


def test_product_price_serialized_as_float():
    """Numeric(12,2) возвращает Decimal — _to_dict обязан отдать float (JSON-сериализуемо)."""
    p = _make_product(price=Decimal("1999.99"))
    d = ProductRepository._to_dict(p)
    assert d["price"] == 1999.99
    assert isinstance(d["price"], float)


def test_product_variant_price_serialized_as_float():
    p = _make_product(variants=[ProductVariant(sku="T-1", price=Decimal("9.99"), stock=3)])
    d = ProductRepository._to_dict(p)
    assert d["variants"][0]["price"] == 9.99
    assert isinstance(d["variants"][0]["price"], float)


def test_price_none_stays_none():
    d = ProductRepository._to_dict(_make_product(price=None))
    assert d["price"] is None


# ---------------------------------------------------------------------------
# _safe_float: строки, Decimal, None, мусор
# ---------------------------------------------------------------------------


def test_safe_float_from_decimal():
    assert _safe_float(Decimal("19.99")) == 19.99


def test_safe_float_from_string():
    assert _safe_float("1 499,50".replace(" ", "").replace(",", ".")) == 1499.5


def test_safe_float_none_returns_default():
    assert _safe_float(None) == 0.0
    assert _safe_float(None, default=42.0) == 42.0


def test_safe_float_garbage_returns_default():
    assert _safe_float("не число") == 0.0
    assert _safe_float(object(), default=1.5) == 1.5


# ---------------------------------------------------------------------------
# _base_source: защита от накопления «A → B → B → B»
# ---------------------------------------------------------------------------


def test_base_source_strips_chain():
    assert _base_source("Магнит Маркет (Файл) → Ozon → Ozon → Ozon") == "Магнит Маркет (Файл)"


def test_base_source_empty():
    assert _base_source("") == "неизвестно"
    assert _base_source(None) == "неизвестно"


# ---------------------------------------------------------------------------
# Стемминг русских окончаний (подбор категории)
# ---------------------------------------------------------------------------


def test_stem_ru_singular_plural_same_stem():
    assert _stem_ru("футболка") == _stem_ru("футболки")
    assert _stem_ru("платье") == _stem_ru("платья")


def test_stem_ru_short_words_unchanged():
    assert _stem_ru("дом") == "дом"


# ---------------------------------------------------------------------------
# Хелперы XLSX
# ---------------------------------------------------------------------------


def test_generate_ean13_valid_checksum():
    """Контрольная цифра должна удовлетворять правилу GS1 (независимая проверка)."""
    ean = _generate_ean13({"id": 12345})
    assert len(ean) == 13
    digits = [int(c) for c in ean]
    total = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
    check = (10 - total % 10) % 10
    assert digits[12] == check
    assert ean.startswith("200")


def test_slug_and_norm():
    assert _slug("Одежда / Футболки") == "Одежда_Футболки"
    assert _norm("Бренд Одежды и Обуви!") == "брендодеждыиобуви"


def test_strip_html():
    assert _strip_html("<p>Хлопок&nbsp;100%</p><br/>") == "Хлопок 100%"
