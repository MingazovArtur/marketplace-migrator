"""
Билдер книги AliExpress: структура 1:1 с официальным XLSX-шаблоном AliExpress Russia
(«Товары → Массовые операции Excel → Загрузить → Скачать шаблон категории»).

Структура листа «Шаблон» (по официальной документации и скриншотам):
  строка 1 — названия блоков (объединённые ячейки):
      «Основные характеристики»,
      «Произвольные характеристики продавца» (5 колонок),
      «Информация о модификации товара (SKU). Товары с разной модификацией,
       но одинаковым SPU ID объединяются в одну карточку»;
  строка 2 — подсказки над полями (допустимые значения, длины, форматы);
  строка 3 — заголовки колонок (обязательные отмечены звёздочкой *),
             здесь же — названия произвольных характеристик продавца;
  строка 4+ — данные (одна строка = одна модификация / SKU).

Вариации разворачиваются в отдельные строки: одинаковый «Модель (seller SPU ID)»,
уникальный «Артикул/Штрихкод (seller SKU ID)», уникальные Цвет/Размер.

Р18 (разбиение монолита services/xlsx_generator/aliexpress.py, 604 строки, на
под-пакет — по прецеденту database/repository/products/, docs/engineering.md):

  - _layout.py    — строки шапки, блоки, колонки (AE_MAIN/AE_SKU), норм-ключи,
                    стили заливок/шрифтов
  - _rows.py      — aliexpress_custom_attr_names, aliexpress_flat_rows
  - _workbook.py  — build_aliexpress_workbook (лист «Шаблон»: блоки, подсказки,
                    заголовки, выпадающие списки, данные, ширины/высоты)
  - _sheets.py    — текстовые листы «Инструкция» и «Требования к изображениям»
  - _utils.py     — _column_index, _count_lines, _fit_header_heights,
                    _write_cell, _set_width

Публичный API сохранён без изменений: `from services.xlsx_generator.aliexpress
import build_aliexpress_workbook, aliexpress_flat_rows,
aliexpress_example_products` (импортёры export_builder.py, routers/export/files.py,
routers/templates.py, xlsx_generator/__init__.py НЕ менялись).
"""

from services.xlsx_generator.aliexpress._layout import (
    AE_CUSTOM_BLOCK,
    AE_CUSTOM_HINT,
    AE_MAIN_BLOCK,
    AE_MAIN_COLUMNS,
    AE_SKU_BLOCK,
    AE_SKU_COLUMNS,
    AE_STANDARD_NORMS,
    BLOCK_FILLS,
    BLOCK_FONT,
    BLOCK_ROW,
    CUSTOM_ATTR_COUNT,
    DATA_FONT,
    DATA_START_ROW,
    HEADER_FONT,
    HEADER_REQUIRED_FONT,
    HEADER_ROW,
    HINT_FONT,
    HINT_ROW,
    WRAP,
)
from services.xlsx_generator.aliexpress._rows import (
    aliexpress_custom_attr_names,
    aliexpress_flat_rows,
)
from services.xlsx_generator.aliexpress._workbook import build_aliexpress_workbook

__all__ = [
    # Публичный API
    "aliexpress_custom_attr_names",
    "aliexpress_flat_rows",
    "build_aliexpress_workbook",
    "aliexpress_example_products",
    # Константы (для совместимости с монолитом)
    "BLOCK_ROW",
    "HINT_ROW",
    "HEADER_ROW",
    "DATA_START_ROW",
    "CUSTOM_ATTR_COUNT",
    "AE_MAIN_BLOCK",
    "AE_CUSTOM_BLOCK",
    "AE_SKU_BLOCK",
    "AE_CUSTOM_HINT",
    "AE_MAIN_COLUMNS",
    "AE_SKU_COLUMNS",
    "AE_STANDARD_NORMS",
    "BLOCK_FILLS",
    "BLOCK_FONT",
    "HINT_FONT",
    "HEADER_FONT",
    "HEADER_REQUIRED_FONT",
    "DATA_FONT",
    "WRAP",
]


# ==================== Демо-пример из официальной документации ====================


def aliexpress_example_products() -> list[dict]:
    """
    Демо-товар из скриншота официального шаблона: свитер с вариациями
    цветов (Красный / Белый) и размеров (S / M) — 4 строки SKU.
    """
    return [
        {
            "id": 1,
            "sku": "SW01",
            "name": "Свитер вязаный хлопковый оверсайз",
            "price": 2490,
            "stock": 15,
            "description": "Тёплый свитер из натурального хлопка, подходит для повседневной носки.",
            "brand": "NONE",
            "barcode": "3545345",
            "category": "Одежда / Свитеры и кофты",
            "photos": [
                "https://example.ru/upload/sweater_main.jpg",
                "https://example.ru/upload/sweater_2.jpg",
            ],
            "package_weight_grams": 450,
            "package_length_mm": 300,
            "package_width_mm": 250,
            "package_height_mm": 50,
            "variants": [
                {"sku": "32423535", "barcode": "3545345", "color": "Красный", "size": "S", "stock": 5, "price": 2490},
                {"sku": "32423536", "barcode": "3545347", "color": "Белый", "size": "M", "stock": 4, "price": 2490},
                {"sku": "32423537", "barcode": "3545348", "color": "Красный", "size": "M", "stock": 3, "price": 2490},
                {"sku": "32423538", "barcode": "3545349", "color": "Белый", "size": "S", "stock": 3, "price": 2490},
            ],
            "attributes": [
                {"name": "Сезон", "value": "Демисезон"},
                {"name": "Состав", "value": "50% хлопок, 50% акрил"},
            ],
        }
    ]
