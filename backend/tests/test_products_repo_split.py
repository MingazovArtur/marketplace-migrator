"""Р14: гарантия, что разбиение database/repository/products.py (593 строки)
на пакет миксинов сохранило публичный API и поведение.

Импортёры НЕ менялись: database/repository/__init__.py
(`from database.repository.products import ProductRepository, repo`),
repository/variants.py и repository/attributes.py (обращаются к
статическим хелперам через класс: `ProductRepository._variant_rows` /
`._attr_rows`), tests/test_money_helpers.py (`ProductRepository._to_dict`
— остаётся зелёным без правок, это тест эквивалентности сериализации).
"""

from decimal import Decimal

from database.models import Product, ProductVariant
from database.repository.products import ProductRepository, repo
import database.repository.products as pkg
from database.repository.products import (
    _async_reads,
    _bulk_import,
    _filters,
    _repository,
    _serialize,
    _sync_reads,
    _writes,
)

ALL_METHODS = {
    # сериализация
    "_to_dict",
    # фильтры
    "_apply_filters",
    "_apply_async_filters",
    # асинхронный контур
    "get_all_async",
    "get_by_id_async",
    "get_stats_async",
    # синхронное чтение
    "get_all",
    "get_by_id",
    "find_by_external",
    "get_by_ids",
    "get_stats",
    # запись
    "add",
    "update",
    "bulk_update",
    "update_batch",
    "delete",
    # P-2 пакетный импорт
    "_import_payload",
    "_variant_rows",
    "_attr_rows",
    "bulk_import",
}


def test_public_api_preserved():
    # те же объекты, что в подмодуле сборки
    assert pkg.ProductRepository is _repository.ProductRepository
    assert pkg.repo is _repository.repo
    assert pkg.repo is repo
    # имена пакета — только публичный API, без случайных имён
    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {"ProductRepository", "repo"}


def test_repository_package_reexport_is_same_object():
    # from database.repository import repo — тот же экземпляр (импортёр __init__.py не менялся)
    from database.repository import ProductRepository as PR2, repo as repo2

    assert PR2 is ProductRepository
    assert repo2 is repo


def test_method_catalog_complete():
    # все 20 методов монолита (17 публичных + 3 статических хелпера) на классе
    missing = {m for m in ALL_METHODS if not hasattr(ProductRepository, m)}
    assert not missing, f"потеряны методы: {missing}"
    assert len(ALL_METHODS) == 20


def test_class_assembled_from_six_mixins():
    from database.repository.products._async_reads import _AsyncReadsMixin
    from database.repository.products._bulk_import import _BulkImportMixin
    from database.repository.products._filters import _FiltersMixin
    from database.repository.products._serialize import _SerializeMixin
    from database.repository.products._sync_reads import _SyncReadsMixin
    from database.repository.products._writes import _WritesMixin

    bases = ProductRepository.__mro__[:-1]  # без object
    assert set(bases) == {
        ProductRepository,
        _SerializeMixin,
        _FiltersMixin,
        _AsyncReadsMixin,
        _SyncReadsMixin,
        _WritesMixin,
        _BulkImportMixin,
    }
    # MRO: сериализация первой (методы чтения зовут self._to_dict)
    assert ProductRepository.__mro__[1] is _SerializeMixin


def test_static_helpers_callable_via_class():
    # variant_repo/attr_repo/test_money_helpers обращаются через КЛАСС —
    # после разбивки хелперы должны быть доступны так же
    assert ProductRepository._to_dict(None) is None
    assert callable(ProductRepository._variant_rows)
    assert callable(ProductRepository._attr_rows)
    assert callable(ProductRepository._import_payload)


def test_variant_rows_skip_empty_sku():
    rows = ProductRepository._variant_rows(
        7,
        [
            {"sku": "  T-1  ", "size": " M ", "price": 10, "stock": 2},
            {"sku": "   ", "size": "L"},          # пустой SKU — пропущен
            {"size": "XL"},                        # SKU нет — пропущен
            {"sku": "T-2"},
        ],
    )
    assert [r.sku for r in rows] == ["T-1", "T-2"]
    assert rows[0].product_id == 7
    assert rows[0].size == "M"
    assert rows[0].price == 10
    assert rows[0].stock == 2
    # sort_order по умолчанию — индекс в исходном списке
    assert rows[0].sort_order == 0
    assert rows[1].sort_order == 3


def test_variant_rows_strip_and_none():
    rows = ProductRepository._variant_rows(
        1, [{"sku": "T-9", "color": "  Красный ", "size": "", "external_id": "ext-9"}]
    )
    assert rows[0].color == "Красный"
    assert rows[0].size is None          # пустая строка → None
    assert rows[0].external_id == "ext-9"


def test_attr_rows_skip_empty_name_or_value():
    rows = ProductRepository._attr_rows(
        3,
        [
            {"name": " Цвет ", "value": " синий ", "platform_attribute_id": 42},
            {"name": "", "value": "x"},    # без имени — пропущен
            {"name": "Материал"},          # без значения — пропущен
            {"name": "Бренд", "value": "A"},
        ],
    )
    assert [(r.name, r.value) for r in rows] == [("Цвет", "синий"), ("Бренд", "A")]
    assert rows[0].product_id == 3
    assert rows[0].platform_attribute_id == 42
    assert rows[0].sort_order == 0
    assert rows[1].sort_order == 3


def test_import_payload_defaults():
    payload, variants, attributes = ProductRepository._import_payload({}, user_id=5, source_label="Ozon (Файл)")
    assert payload["user_id"] == 5
    assert payload["source"] == "Ozon (Файл)"
    assert payload["price"] == 0
    assert payload["status"] == "pending"
    assert payload["description"] == ""
    assert payload["photos"] == []
    assert payload["photos_count"] == 0
    assert payload["category"] == "Не указана"
    assert payload["sku_count"] == 1
    assert payload["units_per_item"] == 1
    assert payload["barcode"] is None
    assert payload["vat_rate"] is None
    assert payload["okpd_code"] is None
    assert variants == []
    assert attributes == []


def test_import_payload_okpd_fallback_chain():
    # окдэ из трёх ключей парсеров: okpd_code → tn_ved → okpd2
    p_okpd, _, _ = ProductRepository._import_payload(
        {"okpd_code": "01.11", "tn_ved": "6109"}, 1, "S"
    )
    p_tnved, _, _ = ProductRepository._import_payload({"tn_ved": "6109"}, 1, "S")
    p_okpd2, _, _ = ProductRepository._import_payload({"okpd2": "28.41"}, 1, "S")
    assert p_okpd["okpd_code"] == "01.11"
    assert p_tnved["okpd_code"] == "6109"
    assert p_okpd2["okpd_code"] == "28.41"


def test_import_payload_photos_count():
    payload, _, _ = ProductRepository._import_payload(
        {"name": "X", "photos": ["a.jpg", "b.jpg"]}, 9, "S"
    )
    assert payload["photos_count"] == 2
    assert payload["photos"] == ["a.jpg", "b.jpg"]


def test_to_dict_full_shape():
    # _to_dict через класс (как tests/test_money_helpers.py) — полный словарь
    p = Product(
        id=1,
        user_id=7,
        name="Футболка",
        source="Магнит Маркет (Файл)",
        price=Decimal("1999.99"),
        status="pending",
        photos=["a.jpg"],
        photos_count=1,
        sku_count=2,
        stock=5,
        barcode="2001234567890",
        weight_grams=300,
        okpd_code="14.13.10",
        variants=[ProductVariant(sku="T-1", price=Decimal("9.99"), stock=3)],
    )
    d = ProductRepository._to_dict(p)
    assert d["price"] == 1999.99 and isinstance(d["price"], float)
    assert d["photos_count"] == 1
    assert d["photos"] == ["a.jpg"]
    assert d["variants"][0]["price"] == 9.99
    assert d["attributes"] == []
    assert d["barcode"] == "2001234567890"
    assert d["weight_grams"] == 300
    assert d["okpd_code"] == "14.13.10"
