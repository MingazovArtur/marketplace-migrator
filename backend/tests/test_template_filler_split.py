"""Р2: гарантии после разбиения монолита services/template_filler.py на пакет.

1. Публичный API: все имена, которые импортируют потребители
   (роутер экспорта, tasks/matching, xlsx_generator/aliexpress|megamarket|__init__),
   доступны из корня пакета.
2. Сквозной сценарий: сохранение эталона → поиск с фолбэком → заполнение
   шаблона товарами (в tmp-каталоге, БД/Redis не нужны).
"""

import io

import pytest
from openpyxl import Workbook, load_workbook

import services.template_filler as tf
from services.template_filler import _storage


@pytest.fixture
def tmp_templates_dir(tmp_path, monkeypatch):
    d = tmp_path / "templates"
    d.mkdir()
    monkeypatch.setattr(_storage, "TEMPLATES_DIR", d)
    monkeypatch.setattr(_storage, "INDEX_PATH", d / "index.json")
    return d


def _sample_official_xlsx() -> bytes:
    """Минимальный «официальный» шаблон Ozon: шапка в строке 2, пример в строке 5."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Список товаров"
    ws.cell(row=1, column=1, value="Инструкция: заполните шаблон")
    ws.cell(row=2, column=1, value="Артикул")
    ws.cell(row=2, column=2, value="Наименование товара")
    ws.cell(row=2, column=3, value="Предельная цена без акций, руб.")
    ws.cell(row=3, column=1, value="Обязательное поле")
    ws.cell(row=4, column=1, value="Подсказка")
    ws.cell(row=5, column=1, value="EXAMPLE-1")
    ws.cell(row=5, column=2, value="Пример товара")
    ws.cell(row=5, column=3, value=100)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


PRODUCT = {
    "id": 42,
    "sku": "SKU-42",
    "name": "Футболка детская",
    "price": 990,
    "attributes": [{"name": "Бренд", "value": "TestBrand"}],
}


def test_public_api_surface():
    """Все имена, использовавшиеся импортёрами монолита, доступны из пакета."""
    for name in (
        "fill_official_template",
        "has_official_template",
        "template_path",
        "get_template_meta",
        "list_official_templates",
        "list_template_names",
        "read_template_bytes",
        "save_official_template",
        "delete_official_template",
        "validate_template_bytes",
        "_build_enum_fix",
        "_expand_products_for_platform",
        "_norm",
        "_row_values",
        "TEMPLATES_DIR",
        "INDEX_PATH",
    ):
        assert hasattr(tf, name), f"Потеряно имя публичного API: {name}"


def test_validate_and_save_official_template(tmp_templates_dir):
    data = _sample_official_xlsx()
    assert tf.validate_template_bytes(data, platform="ozon") is None
    meta = tf.save_official_template("Одежда", data, uploaded_by="qa", platform="ozon")
    assert meta["platform"] == "ozon"
    assert meta["category_name"] == "Одежда"
    assert meta["columns"] == 3
    assert tf.has_official_template("Одежда", platform="ozon")
    assert tf.list_template_names("ozon") == ["Одежда"]
    # Фолбэк: любая другая категория падает на первый доступный эталон площадки
    assert tf.has_official_template("Несуществующая категория", platform="ozon")


def test_fill_official_template_end_to_end(tmp_templates_dir):
    data = _sample_official_xlsx()
    tf.save_official_template("Одежда", data, platform="ozon")

    result = tf.fill_official_template("Одежда", [PRODUCT], platform="ozon")
    wb = load_workbook(io.BytesIO(result))
    ws = wb["Список товаров"]

    # Шапка осталась оригинальной, пример удалён, наш товар записан
    assert ws.cell(row=2, column=1).value == "Артикул"
    assert ws.cell(row=5, column=1).value == "SKU-42"
    assert ws.cell(row=5, column=2).value == "Футболка детская"
    assert ws.cell(row=5, column=3).value == 990
    # Пример площадки удалён
    values_in_col_a = [
        ws.cell(row=r, column=1).value for r in range(5, ws.max_row + 1)
    ]
    assert "EXAMPLE-1" not in values_in_col_a


def test_row_values_platform_mapping():
    """Ключевые правила площадок сохранены после разреза _row_values в _values.py."""
    vals_ozon = tf._row_values(PRODUCT, 1, {}, platform="ozon")
    assert vals_ozon["артикул"] == "SKU-42"
    assert vals_ozon["предельнаяценабезакцийруб"] == 990

    # Мегамаркет: цена/вес форматируются с запятой, штрихкод генерируется EAN-13
    vals_mm = tf._row_values(PRODUCT, 1, {}, platform="megamarket")
    assert vals_mm["вескг"] == "0,5"  # 500 г дефолт → 0,5 кг
    assert vals_mm["основнойштрихкодgtin"].isdigit() and len(vals_mm["основнойштрихкодgtin"]) == 13

    # AliExpress: вариации разворачиваются в отдельные строки
    prod_var = dict(PRODUCT, variants=[{"sku": "V1", "color": "Красный", "size": "M"}])
    expanded = tf._expand_products_for_platform([prod_var], "aliexpress")
    assert len(expanded) == 1  # aliexpress-ветка требует variants>0 → разворот
    prod_two = dict(
        PRODUCT,
        variants=[
            {"sku": "V1", "color": "Красный"},
            {"sku": "V2", "color": "Синий"},
        ],
    )
    expanded2 = tf._expand_products_for_platform([prod_two], "aliexpress")
    assert len(expanded2) == 2
    assert expanded2[0]["_spu_id"] == expanded2[1]["_spu_id"] == "SKU-42"
    assert expanded2[0]["_article"] == "V1"


def test_delete_official_template(tmp_templates_dir):
    data = _sample_official_xlsx()
    tf.save_official_template("Одежда", data, platform="ozon")
    assert tf.delete_official_template("Одежда", platform="ozon") is True
    assert not tf.has_official_template("Одежда", platform="ozon")
    assert tf.delete_official_template("Одежда", platform="ozon") is False


def test_module_attrs_for_monkeypatch():
    """Модуль _storage доступен из пакета для тестов (monkeypatch путей)."""
    assert str(_storage.TEMPLATES_DIR) == str(tf.TEMPLATES_DIR)
    assert str(_storage.INDEX_PATH) == str(tf.INDEX_PATH)
