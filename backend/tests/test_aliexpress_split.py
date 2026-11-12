"""Р18: гарантия, что разбиение services/xlsx_generator/aliexpress.py (604
строки) на под-пакет сохранило публичный API и поведение.

Импортёры — services/export_builder.py, routers/export/files.py,
routers/templates.py, xlsx_generator/__init__.py: все используют
`from services.xlsx_generator.aliexpress import ...` — после превращения
модуля в под-пакет импорты не менялись. Поведение проверяем на реальной
сборке книги openpyxl (без сети) по демо-примеру из документации AliExpress.
"""

from services.xlsx_generator.aliexpress import (
    aliexpress_custom_attr_names,
    aliexpress_example_products,
    aliexpress_flat_rows,
    build_aliexpress_workbook,
)
from services.xlsx_generator.aliexpress import (
    _layout,
    _rows,
    _sheets,
    _utils,
    _workbook,
)


def test_public_api_preserved():
    import services.xlsx_generator.aliexpress as pkg
    import services.xlsx_generator as xg

    # публичные функции — те же объекты, что в подмодулях
    assert pkg.build_aliexpress_workbook is _workbook.build_aliexpress_workbook
    assert pkg.aliexpress_flat_rows is _rows.aliexpress_flat_rows
    assert pkg.aliexpress_custom_attr_names is _rows.aliexpress_custom_attr_names
    # демо-пример живёт на пакете, как в монолите
    assert pkg.aliexpress_example_products.__module__ == "services.xlsx_generator.aliexpress"
    # реэкспорт из xlsx_generator/__init__ указывает на ту же функцию
    assert xg.build_aliexpress_workbook is pkg.build_aliexpress_workbook

    public = {n for n in dir(pkg) if not n.startswith("_")}
    # полный каталог публичных имён монолита (функции + константы)
    assert public == {
        "AE_CUSTOM_BLOCK",
        "AE_CUSTOM_HINT",
        "AE_MAIN_BLOCK",
        "AE_MAIN_COLUMNS",
        "AE_SKU_BLOCK",
        "AE_SKU_COLUMNS",
        "AE_STANDARD_NORMS",
        "BLOCK_FILLS",
        "BLOCK_FONT",
        "BLOCK_ROW",
        "CUSTOM_ATTR_COUNT",
        "DATA_FONT",
        "DATA_START_ROW",
        "HEADER_FONT",
        "HEADER_REQUIRED_FONT",
        "HEADER_ROW",
        "HINT_FONT",
        "HINT_ROW",
        "WRAP",
        "aliexpress_custom_attr_names",
        "aliexpress_example_products",
        "aliexpress_flat_rows",
        "build_aliexpress_workbook",
    }
    # константы — те же объекты, что в _layout
    assert pkg.AE_MAIN_COLUMNS is _layout.AE_MAIN_COLUMNS
    assert pkg.AE_SKU_COLUMNS is _layout.AE_SKU_COLUMNS
    assert pkg.BLOCK_FILLS is _layout.BLOCK_FILLS
    assert pkg.DATA_START_ROW == 4


def test_layout_constants():
    # строки шапки шаблона: блоки / подсказки / заголовки / данные
    assert (_layout.BLOCK_ROW, _layout.HINT_ROW, _layout.HEADER_ROW, _layout.DATA_START_ROW) == (1, 2, 3, 4)
    assert _layout.CUSTOM_ATTR_COUNT == 5
    assert _layout.AE_MAIN_BLOCK == "Основные характеристики"
    # блоки заливаются разными цветами
    assert len(_layout.BLOCK_FILLS) == 3
    assert set(_layout.BLOCK_FILLS) == {
        _layout.AE_MAIN_BLOCK,
        _layout.AE_CUSTOM_BLOCK,
        _layout.AE_SKU_BLOCK,
    }
    # 9 основных + 12 SKU-колонок; у каждой 4 поля
    assert len(_layout.AE_MAIN_COLUMNS) == 9
    assert len(_layout.AE_SKU_COLUMNS) == 12
    assert all(len(col) == 4 for col in _layout.AE_MAIN_COLUMNS + _layout.AE_SKU_COLUMNS)
    # нормализованные ключи не дублируют друг друга
    keys = [k for _, _, _, k in _layout.AE_MAIN_COLUMNS + _layout.AE_SKU_COLUMNS]
    assert len(keys) == len(set(keys))
    # бренд/цвет/размер/модель/тип — стандартные, произвольные их не дублируют
    assert {"бренд", "цвет", "размер", "модель", "тип"} <= _layout.AE_STANDARD_NORMS


def test_custom_attr_names_filters_standard_and_dedupes():
    products = [
        {
            "attributes": [
                {"name": "Бренд", "value": "Nike"},          # стандартная колонка
                {"name": "  Сезон  ", "value": "Лето"},      # произвольная, strip
                {"name": "Сезон", "value": "Зима"},          # дубль по норме
                {"name": "", "value": "пустое имя"},         # пустое имя
            ]
        },
        {"attributes": [{"name": f"Хар-{i}", "value": "x"} for i in range(7)]},
    ]
    # до 5 произвольных, стандартные и дубли не попадают
    assert aliexpress_custom_attr_names(products) == [
        "Сезон",
        "Хар-0",
        "Хар-1",
        "Хар-2",
        "Хар-3",
    ]


def test_flat_rows_expand_variations():
    rows = aliexpress_flat_rows(aliexpress_example_products())
    # демо-товар: 4 вариации → 4 строки
    assert len(rows) == 4
    # порядок колонок: основные → произвольные → SKU
    headers = list(rows[0].keys())
    assert headers[0] == "Модель (seller SPU ID)"
    assert "Сезон" in headers and "Состав" in headers  # произвольные характеристики
    assert headers[-1] == "Остаток"
    # у всех вариаций одинаковая модель (SPU), уникальные артикулы (SKU)
    models = {r["Модель (seller SPU ID)"] for r in rows}
    skus = {r["Артикул/Штрихкод (seller SKU ID)"] for r in rows}
    assert len(models) == 1
    assert len(skus) == 4
    # цвета/размеры разложены по строкам
    assert {(r["Цвет"], r["Размер"]) for r in rows} == {
        ("Красный", "S"),
        ("Белый", "M"),
        ("Красный", "M"),
        ("Белый", "S"),
    }


def test_build_workbook_structure():
    wb = build_aliexpress_workbook(aliexpress_example_products())
    assert wb.sheetnames == ["Шаблон", "Инструкция", "Требования к изображениям"]

    ws = wb["Шаблон"]
    # строка 1 — блоки; 9 основных колонок слились в один блок
    assert ws.cell(row=1, column=1).value == "Основные характеристики"
    assert ws.cell(row=1, column=10).value == "Произвольные характеристики продавца"
    assert ws.cell(row=1, column=15).value.startswith("Информация о модификации товара")
    # строка 3 — заголовки; обязательные со звёздочкой
    assert ws.cell(row=3, column=1).value == "Модель (seller SPU ID)*"
    assert ws.cell(row=3, column=2).value == "Артикул/Штрихкод (seller SKU ID)*"
    assert ws.cell(row=3, column=4).value == "GTIN"  # необязательная — без звёздочки
    # произвольные характеристики продавца — в заголовках строки 3
    assert ws.cell(row=3, column=10).value == "Сезон"
    assert ws.cell(row=3, column=11).value == "Состав"
    # данные с 4-й строки: 4 вариации демо-товара
    assert ws.cell(row=4, column=1).value == "SW01"
    assert ws.cell(row=4, column=2).value == "32423535"
    assert ws.cell(row=7, column=2).value == "32423538"
    assert ws.cell(row=8, column=1).value is None  # данные кончились
    # шапка закреплена
    assert ws.freeze_panes == "A4"


def test_build_workbook_with_spec_dropdowns():
    spec = {
        "attributes": [
            {"name": "Цвет", "values": ["Красный", "Белый", "Чёрный"]},
            {"name": "Доставка из", "values": ["Россия"]},  # < 2 значений → без списка
        ]
    }
    wb = build_aliexpress_workbook(aliexpress_example_products(), spec)
    ws = wb["Шаблон"]
    # короткий словарь → инлайн-список валидации на колонке «Цвет» (6-я после SKU-старта)
    formulas = [dv.formula1 for dv in ws.data_validations.dataValidation]
    assert '"Красный,Белый,Чёрный"' in formulas
    # один значений → без валидации
    assert '"Россия"' not in formulas


def test_utils_column_index_and_count_lines():
    from services.xlsx_generator.aliexpress._layout import AE_SKU_COLUMNS
    from services.xlsx_generator.aliexpress._utils import _column_index, _count_lines

    sku_start = 10 + 5  # 9 основных + 5 произвольных + 1
    # основная колонка ищется с 1
    assert _column_index("Модель (seller SPU ID)", sku_start) == 1
    # SKU-колонка — со сдвигом
    assert _column_index(AE_SKU_COLUMNS[0][0], sku_start) == sku_start
    # неизвестный заголовок — 1 (не падает)
    assert _column_index("Нет такой", sku_start) == 1

    # перенос текста: пусто → 1 строка, короткий текст → 1, длинный → больше
    assert _count_lines("", 18) == 1
    assert _count_lines("коротко", 18) == 1
    assert _count_lines("а" * 40, 18) == 3  # 40 / (18*0.95≈17) → 3
    assert _count_lines("строка1\nстрока2", 100) == 2


def test_sheets_fill_text_sheet():
    from openpyxl import Workbook

    from services.xlsx_generator.aliexpress._sheets import (
        _build_images_sheet,
        _build_instruction_sheet,
    )

    wb = Workbook()
    _build_instruction_sheet(wb)
    _build_images_sheet(wb)
    instr = wb["Инструкция"]
    assert instr.cell(row=1, column=1).value == "Загрузка товаров через Excel — AliExpress"
    # заголовки разделов выделены жирным
    assert instr.cell(row=3, column=1).font.bold is True
    # однострочный текст — обычный шрифт
    assert instr.cell(row=4, column=1).font.bold is False
    imgs = wb["Требования к изображениям"]
    assert imgs.cell(row=1, column=1).value == "Требования к изображениям"
    # лист вписывается в ширину страницы при печати
    assert imgs.page_setup.fitToWidth == 1
    assert imgs.page_setup.fitToHeight == 0
