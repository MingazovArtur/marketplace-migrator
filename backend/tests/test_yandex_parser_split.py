"""Р24: гарантия, что разбиение parsers/yandex.py (342 строки) на пакет
сохранило публичный API и поведение.

Импортёр один — parsers/factory (реестр PARSERS): `from parsers.yandex
import YandexFileParser` (не менялся); через фасад `from parsers import
parse_file / preview_file / get_parser` (routers/import_router) — те же
объекты.
"""

import io

import openpyxl

import parsers.yandex as pkg
from parsers.yandex._parser import YandexFileParser as from_parser
from parsers.yandex._support import (
    YANDEX_SKIP_MARKERS as from_support_markers,
)
from parsers.yandex._support import (
    _cm_to_mm as from_support_cm,
)
from parsers.yandex._support import (
    _kg_to_grams as from_support_kg,
)
from parsers.yandex._support import (
    _parse_yandex_characteristics as from_support_chars,
)


def test_public_api_preserved():
    assert pkg.YandexFileParser is from_parser
    assert pkg.YANDEX_SKIP_MARKERS is from_support_markers
    assert pkg._cm_to_mm is from_support_cm
    assert pkg._kg_to_grams is from_support_kg
    assert pkg._parse_yandex_characteristics is from_support_chars
    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {"YandexFileParser", "YANDEX_SKIP_MARKERS"}


def test_skip_markers_cover_service_rows():
    # маркеры строки-подсказки (строка 3) и строки-примера (строка 4) шаблона
    assert "это пример с заполненными полями" in from_support_markers
    assert "укажите свой товар или удалите строку" in from_support_markers
    assert "дрель makita 6413 безударная" in from_support_markers


def test_unit_converters():
    assert from_support_cm("65.55") == 656
    assert from_support_cm("65,55") == 656
    assert from_support_cm("0") is None
    assert from_support_cm("-5") is None
    assert from_support_cm("abc") is None
    assert from_support_cm("") is None
    assert from_support_kg("1.001") == 1001
    assert from_support_kg("0.5") == 500
    assert from_support_kg(None) is None


def test_parse_characteristics_format():
    assert from_support_chars("Цвет|Красный") == [{"name": "Цвет", "value": "Красный"}]
    # третья часть — единица измерения, приклеивается к значению
    assert from_support_chars("Длина|100|см") == [{"name": "Длина", "value": "100 см"}]
    # мусор и пустота отбрасываются
    assert from_support_chars("мусор; ; Цвет|Красный") == [{"name": "Цвет", "value": "Красный"}]
    assert from_support_chars("") == []
    assert from_support_chars(None) == []


def _ym_xlsx(rows: list[list], sheet: str = "Список товаров") -> bytes:
    """Собирает XLSX как шаблон Яндекс Маркета: строка 1 — пустая, строка 2 — шапка."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append([])  # строка 1: под группой
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADERS = [
    "Ваш SKU *",
    "Название товара *",
    "Ссылка на изображение *",
    "Описание товара *",
    "Категория на Маркете *",
    "Бренд *",
    "Штрихкод *",
    "Вес, кг *",
    "Длина, см *",
    "Ширина, см *",
    "Высота, см *",
    "Цена *",
    "ТН ВЭД *",
    "Характеристики товара",
    "Остаток",
]
GOOD_ROW = [
    "T-100",
    "Футболка с принтом",
    "http://x/1.jpg; http://x/2.jpg",
    "Хлопок 100%",
    "Одежда / Футболки",
    "Adidas",
    "4600000000000",
    "1.001",
    "65.55",
    "40",
    "5",
    "1 499,50",
    "6109",
    "Цвет|Красный; Состав|Хлопок",
    "12",
]


def test_parser_xlsx_full_product():
    content = _ym_xlsx(
        [
            HEADERS,
            ["значение поля выгружено автоматически", *[""] * (len(HEADERS) - 1)],  # подсказка (строка 3)
            ["123456", "Дрель Makita 6413 безударная", *[""] * (len(HEADERS) - 2)],  # пример (строка 4)
            GOOD_ROW,
        ]
    )
    parser = from_parser()
    result = parser.parse(content, "xlsx")

    # подсказка и пример пропущены, остался один товар
    assert result.imported == 1 and result.errors == []
    p = result.products[0]
    assert p["sku"] == "T-100"
    assert p["name"] == "Футболка с принтом"
    assert p["price"] == 1499.5
    assert p["barcode"] == "4600000000000"
    assert p["photos"] == ["http://x/1.jpg", "http://x/2.jpg"]
    assert p["category"] == "Одежда / Футболки"
    assert p["brand"] == "Adidas"
    # конвертеры единиц шаблона: кг→г, см→мм
    assert p["package_weight_grams"] == 1001
    assert p["package_length_mm"] == 656
    assert p["package_width_mm"] == 400
    assert p["package_height_mm"] == 50
    # ТН ВЭД и характеристики
    assert p["okpd_code"] == "6109"
    assert p["attributes"] == [
        {"name": "Цвет", "value": "Красный"},
        {"name": "Состав", "value": "Хлопок"},
    ]
    assert p["stock"] == 12
    assert result.total_rows == 1


def test_parser_xlsx_empty_name_is_error():
    # sku указан, названия нет → ошибка «Пустое название товара»
    row = ["T-100", ""] + list(GOOD_ROW[2:])
    content = _ym_xlsx([HEADERS, row])
    result = from_parser().parse(content, "xlsx")
    assert result.imported == 0
    assert result.errors and result.errors[0]["error"] == "Пустое название товара"
    assert result.errors[0]["row"] == 3  # шапка в строке 2, товар — в строке 3


def test_parser_xlsx_no_header_raises():
    content = _ym_xlsx([["что", "угодно"], ["без", "шапки"]])
    import pytest

    with pytest.raises(ValueError, match="строка заголовков"):
        from_parser().parse(content, "xlsx")


def test_parser_flat_csv():
    csv = "Ваш SKU,Название товара,Цена,Бренд,Категория\nT-1,Товар,1990,Adidas,Дом\n".encode()
    result = from_parser().parse(csv, "csv")
    assert result.imported == 1
    p = result.products[0]
    assert p["sku"] == "T-1"
    assert p["name"] == "Товар"
    assert p["price"] == 1990.0
    assert p["category"] == "Дом"


def test_parser_empty_csv_warning():
    result = from_parser().parse("Название товара\n".encode(), "csv")
    # только шапка → файл «пустой» по товарам, предупреждение
    assert result.imported == 0
    assert result.warnings == [{"type": "empty", "message": "Файл пуст"}]


def test_platform_and_formats():
    parser = from_parser()
    assert parser.platform == "yandex"
    assert parser.supported_formats == ["xlsx", "csv"]
