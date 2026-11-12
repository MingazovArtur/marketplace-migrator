"""Р19: гарантия, что разбиение services/xlsx_generator/columns.py (597 строк)
на под-пакет сохранило публичный API и данные.

Импортёры — common/yandex/ozon/simple внутри пакета xlsx_generator: все
используют `from services.xlsx_generator.columns import ...` — после
превращения модуля в под-пакет импорты не менялись. Значения всех констант
проверяются на целостность против официальных шаблонов (число колонок,
заголовки, обязательность, объединения групп).
"""

import services.xlsx_generator.columns as pkg
from services.xlsx_generator.columns import (
    _ozon,
    _styles,
    _yandex,
)


def test_public_api_preserved():
    # все константы — те же объекты, что в подмодулях
    assert pkg.OZON_BASE_COLUMNS is _ozon.OZON_BASE_COLUMNS
    assert pkg.YANDEX_TEMPLATE_COLUMNS is _yandex.YANDEX_TEMPLATE_COLUMNS
    assert pkg.YANDEX_GROUP_MERGES is _yandex.YANDEX_GROUP_MERGES
    assert pkg.RED_FILL is _styles.RED_FILL
    assert pkg.G_NAME is _styles.G_NAME
    assert pkg.BRAND_NAMES is _styles.BRAND_NAMES

    public = {n for n in dir(pkg) if not n.startswith("_")}
    assert public == {
        # стили
        "RED_FILL", "GRAY_FILL", "YM_HINT_FILL", "HEADER_FONT",
        "RED_HEADER_FONT", "GROUP_FONT", "HINT_FONT", "DATA_FONT",
        "THIN_SIDE", "CELL_BORDER",
        # общие константы
        "DICT_LIMIT", "DATA_START_ROW", "VAT_LABELS",
        # группы Ozon
        "G_NAME", "G_PRICE", "G_PROMO", "G_SKU", "G_EXTRA",
        "G_UNION", "G_VARIANT", "G_ATTRS",
        # справочники
        "BRAND_NAMES", "RECOMMENDED_ONLY",
        # подсказки
        "HINT_MAIN_PHOTO", "HINT_EXTRA_PHOTOS",
        # колонки
        "OZON_BASE_COLUMNS", "YANDEX_TEMPLATE_COLUMNS", "YANDEX_GROUP_MERGES",
    }


def test_importers_path_unchanged():
    # главный путь импортёров продолжает работать буквально
    from services.xlsx_generator.columns import (
        BRAND_NAMES,
        CELL_BORDER,
        DICT_LIMIT,
        G_ATTRS,
        G_UNION,
        G_VARIANT,
        HEADER_FONT,
        OZON_BASE_COLUMNS,
        RECOMMENDED_ONLY,
        RED_FILL,
        VAT_LABELS,
        YANDEX_GROUP_MERGES,
        YANDEX_TEMPLATE_COLUMNS,
        YM_HINT_FILL,
    )

    assert BRAND_NAMES and CELL_BORDER and DICT_LIMIT  # noqa: городим использование
    assert all(x is not None for x in (G_ATTRS, G_UNION, G_VARIANT, HEADER_FONT))


def test_common_constants():
    assert pkg.DATA_START_ROW == 5
    assert pkg.DICT_LIMIT == 5000
    assert pkg.VAT_LABELS == {"none": "Не облагается", "22": "22", "10": "10", "7": "7", "5": "5"}
    assert pkg.BRAND_NAMES == {"бренд", "бренд в одежде и обуви", "брендодеждыиобуви"}
    assert pkg.RECOMMENDED_ONLY == {"российский размер", "пол"}


def test_ozon_columns_integrity():
    cols = pkg.OZON_BASE_COLUMNS
    # 18 колонок, у каждой 6 полей (заголовок, ключ, обязательная, тип, подсказка, группа)
    assert len(cols) == 18
    assert all(len(c) == 6 for c in cols)
    headers = [c[0] for c in cols]
    assert headers[0] == "№"
    assert headers[1] == "Артикул"
    assert headers[-1] == "Артикул фото"
    # обязательные колонки Ozon
    required = {c[0] for c in cols if c[2]}
    assert {
        "Артикул",
        "Предельная цена без акций, руб.",
        "НДС, %",
        "ТН ВЭД коды ЕАЭС",
        "Вес в упаковке, г",
        "Ширина упаковки, мм",
        "Высота упаковки, мм",
        "Длина упаковки, мм",
        "Ссылка на главное фото",
    } <= required
    # группы ссылаются на общие тексты _styles (те же объекты)
    by_header = {c[0]: c for c in cols}
    assert by_header["Название товара"][5] is pkg.G_NAME
    assert by_header["Предельная цена без акций, руб."][5] is pkg.G_PRICE
    assert by_header["Рассрочка"][5] is pkg.G_PROMO
    assert by_header["SKU"][5] is pkg.G_SKU
    assert by_header["Вес в упаковке, г"][5] is pkg.G_EXTRA
    # подсказки фото — общие константы
    assert by_header["Ссылка на главное фото"][4] is pkg.HINT_MAIN_PHOTO
    assert by_header["Ссылки на дополнительные фото"][4] is pkg.HINT_EXTRA_PHOTOS


def test_yandex_columns_integrity():
    cols = pkg.YANDEX_TEMPLATE_COLUMNS
    # 48 колонок официального шаблона, у каждой 6 полей
    assert len(cols) == 48
    assert all(len(c) == 6 for c in cols)
    # крайние колонки: информационные справа, обязательные в середине
    assert cols[0][0] == "Критичные ошибки"
    assert cols[0][3] is True  # информационная (readonly)
    assert cols[3][0] == "Ваш SKU *"
    assert cols[3][2] is True  # обязательная
    assert cols[-1][0] == "Дата дополнения карточки"
    assert cols[-1][3] is True
    # количество обязательных колонок (SKU, название, фото, описание,
    # категория, бренд, штрихкод, вес, габариты ×3, цена, ТН ВЭД)
    assert sum(1 for c in cols if c[2]) == 13
    # уникальные заголовки
    headers = [c[0] for c in cols]
    assert len(headers) == len(set(headers))
    # ключи значений уникальны и непустые у заполняемых колонок
    keys = [c[1] for c in cols if c[1] is not None]
    assert len(keys) == len(set(keys))
    assert "okpd_code" in keys and "price" in keys  # ТН ВЭД и Цена


def test_yandex_group_merges():
    # 10 объединений групп, колонки 1–48, без пересечений, по возрастанию
    merges = pkg.YANDEX_GROUP_MERGES
    assert len(merges) == 10
    prev_end = 0
    covered = 0
    for start, end in merges:
        assert 1 <= start <= end <= 48
        assert start > prev_end  # непересекающиеся и по порядку
        covered += end - start + 1
        prev_end = end
    # группы покрывают все 48 колонок без дыр
    assert covered == 48
    assert prev_end == 48


def test_group_texts_are_strings_with_hints():
    # тексты групп Ozon: «заголовок\nподсказка» (G_NAME — только заголовок)
    for g in (pkg.G_PRICE, pkg.G_PROMO, pkg.G_SKU, pkg.G_EXTRA,
              pkg.G_UNION, pkg.G_VARIANT, pkg.G_ATTRS):
        assert isinstance(g, str) and "\n" in g
    # G_NAME — короткий заголовок без подсказки
    assert pkg.G_NAME == "Название"
