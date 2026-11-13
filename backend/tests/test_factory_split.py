"""Р25: гарантия, что разбиение parsers/factory.py (334 строки) на пакет
сохранило публичный API, реестр и поведение.

Импортёр один — parsers/__init__.py: `from .factory import parse_file,
preview_file, get_parser` (не менялся); дальше `from parsers import ...`
(routers/import_router/_file_import.py и /_preview.py — не менялись).
"""

import parsers.factory as pkg
import parsers.factory._smart as smart_mod
from parsers.base import BaseFileParser
from parsers.factory._api import (
    get_parser as from_api_get,
    parse_file as from_api_parse,
    preview_file as from_api_preview,
)
from parsers.factory._registry import PARSERS as from_registry_parsers
from parsers.factory._smart import SmartMarketplaceParser as from_smart


def test_public_api_preserved():
    assert pkg.parse_file is from_api_parse
    assert pkg.preview_file is from_api_preview
    assert pkg.get_parser is from_api_get
    assert pkg.PARSERS is from_registry_parsers
    assert pkg.SmartMarketplaceParser is from_smart
    # полный каталог поверхности пакета
    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {
        "PARSERS",
        "AliexpressFileParser",
        "HolodilnikFileParser",
        "MegamarketFileParser",
        "SmartMarketplaceParser",
        "get_parser",
        "parse_file",
        "preview_file",
    }


def test_parsers_facade_reexport():
    # `from parsers import parse_file, preview_file, get_parser` — те же объекты
    from parsers import get_parser, parse_file, preview_file

    assert parse_file is from_api_parse
    assert preview_file is from_api_preview
    assert get_parser is from_api_get


def test_registry_seven_platforms():
    assert set(from_registry_parsers) == {
        "ozon",
        "magnit",
        "wildberries",
        "yandex",
        "megamarket",
        "holodilnik",
        "aliexpress",
    }
    # подклассы Smart-парсера наследуют универсальную логику
    assert issubclass(pkg.MegamarketFileParser, from_smart)
    assert issubclass(pkg.HolodilnikFileParser, from_smart)
    assert issubclass(pkg.AliexpressFileParser, from_smart)
    # все парсеры — BaseFileParser
    assert all(issubclass(cls, BaseFileParser) for cls in from_registry_parsers.values())


def test_get_parser_platforms():
    assert from_api_get("yandex").platform == "yandex"
    assert type(from_api_get("megamarket")).__name__ == "MegamarketFileParser"
    assert from_api_get("MAGNIT  ").platform == "magnit"  # нормализация регистра/пробелов


def test_get_parser_unknown_raises():
    import pytest

    with pytest.raises(ValueError) as ei:
        from_api_get("ebay")
    assert "не реализован" in str(ei.value)
    assert "ozon" in str(ei.value)  # сообщение перечисляет доступные


def test_parse_file_format_gate():
    import pytest

    with pytest.raises(ValueError, match="не поддерживает формат"):
        from_api_parse(b"", "yandex", "yml")


def _smart_csv(rows: list[list[str]]) -> bytes:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def test_smart_parser_csv_products():
    content = _smart_csv(
        [
            ["Артикул", "Название товара", "Цена", "Бренд", "Категория", "Остаток"],
            ["A-1", "Телевизор Samsung", "39990 руб.", "Samsung", "Электроника", "5"],
            ["A-2", "Пылесос", "7 499,50", "Polaris", "Техника для дома", ""],
        ]
    )
    # SmartMarketplaceParser абстрактен (platform без реализации) — тестируем
    # через подкласс, ровно как делает реестр PARSERS
    parser = pkg.MegamarketFileParser()
    result = parser.parse(content, "csv")

    assert result.imported == 2
    p1, p2 = result.products
    assert p1["sku"] == "A-1" and p1["name"] == "Телевизор Samsung"
    assert p1["price"] == 39990.0 and p1["stock"] == 5
    assert p2["sku"] == "A-2" and p2["price"] == 7499.5
    assert p2["stock"] == 10  # отсутствие остатка → дефолт 10
    assert p1["external_id"] == "A-1"


def test_smart_parser_skips_hint_rows_and_generates_sku():
    content = _smart_csv(
        [
            ["Артикул", "Название товара", "Цена"],
            ["", "Уникальный артикул товара в каталоге продавца", ""],  # строка-подсказка
            ["", "Товар без SKU", "100"],
        ]
    )
    parser = pkg.MegamarketFileParser()
    result = parser.parse(content, "csv")

    # подсказка пропущена; товар без SKU получил сгенерированный артикул
    assert result.imported == 1
    p = result.products[0]
    assert p["name"] == "Товар без SKU"
    assert p["sku"].startswith("IMP-")


def test_smart_parser_parse_error_recorded():
    # мусорные байты как XLSX падают на открытии книги: парсер не роняет
    # исключение наружу, фиксирует ошибку в errors (ровно как в монолите)
    result = pkg.MegamarketFileParser().parse(b"\xff\xfe\xff not a zip", "xlsx")
    assert result.products == []
    assert result.errors  # ошибка зафиксирована, исключение не прокинуто


def test_preview_file_structure():
    rows = [["Артикул", "Название товара", "Цена"]]
    rows += [[f"A-{i}", f"Товар {i}", "100"] for i in range(15)]
    content = _smart_csv(rows)
    preview = from_api_preview(content, "megamarket", "csv", max_rows=5)

    assert set(preview) == {
        "columns",
        "preview",
        "total_estimated",
        "valid_estimated",
        "errors",
        "warnings",
    }
    assert len(preview["preview"]) == 5  # max_rows обрезает
    assert preview["total_estimated"] == 15
    assert preview["valid_estimated"] == 15
    # колонки — ключи словаря товара в порядке вставки
    assert preview["columns"] == [
        "external_id", "sku", "name", "price", "description",
        "brand", "barcode", "category", "stock", "photos",
    ]
