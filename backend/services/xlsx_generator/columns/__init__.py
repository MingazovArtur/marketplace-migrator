"""
Константы структуры XLSX-шаблонов площадок: колонки Ozon/Яндекс Маркета,
стили ячеек, тексты групп и подсказок.

Выделено из монолитного services/xlsx_generator.py (E-7, неделя 4).
Используется всеми билдерами пакета services.xlsx_generator.

Р19 (разбиение монолита columns.py, 597 строк, на под-пакет — по прецеденту
database/repository/products/, docs/engineering.md):

  - _styles.py  — стили ячеек, границы, тексты групп Ozon (G_*), подсказки,
                  VAT_LABELS, BRAND_NAMES, RECOMMENDED_ONLY, DICT_LIMIT,
                  DATA_START_ROW
  - _ozon.py    — OZON_BASE_COLUMNS (18 колонок базового шаблона Ozon)
  - _yandex.py  — YANDEX_TEMPLATE_COLUMNS (48 колонок официального шаблона
                  Яндекс Маркета), YANDEX_GROUP_MERGES

Публичный API сохранён без изменений: `from services.xlsx_generator.columns
import ...` (импортёры common/yandex/ozon/simple НЕ менялись) — все константы
реэкспортируются здесь теми же объектами.
"""

from services.xlsx_generator.columns._ozon import OZON_BASE_COLUMNS
from services.xlsx_generator.columns._styles import (
    BRAND_NAMES,
    CELL_BORDER,
    DATA_FONT,
    DATA_START_ROW,
    DICT_LIMIT,
    G_ATTRS,
    G_EXTRA,
    G_NAME,
    G_PRICE,
    G_PROMO,
    G_SKU,
    G_UNION,
    G_VARIANT,
    GRAY_FILL,
    GROUP_FONT,
    HEADER_FONT,
    HINT_EXTRA_PHOTOS,
    HINT_FONT,
    HINT_MAIN_PHOTO,
    RECOMMENDED_ONLY,
    RED_FILL,
    RED_HEADER_FONT,
    THIN_SIDE,
    VAT_LABELS,
    YM_HINT_FILL,
)
from services.xlsx_generator.columns._yandex import (
    YANDEX_GROUP_MERGES,
    YANDEX_TEMPLATE_COLUMNS,
)

__all__ = [
    # Стили
    "RED_FILL",
    "GRAY_FILL",
    "YM_HINT_FILL",
    "HEADER_FONT",
    "RED_HEADER_FONT",
    "GROUP_FONT",
    "HINT_FONT",
    "DATA_FONT",
    "THIN_SIDE",
    "CELL_BORDER",
    # Общие константы
    "DICT_LIMIT",
    "DATA_START_ROW",
    "VAT_LABELS",
    # Группы Ozon
    "G_NAME",
    "G_PRICE",
    "G_PROMO",
    "G_SKU",
    "G_EXTRA",
    "G_UNION",
    "G_VARIANT",
    "G_ATTRS",
    # Справочники
    "BRAND_NAMES",
    "RECOMMENDED_ONLY",
    # Подсказки
    "HINT_MAIN_PHOTO",
    "HINT_EXTRA_PHOTOS",
    # Колонки
    "OZON_BASE_COLUMNS",
    "YANDEX_TEMPLATE_COLUMNS",
    "YANDEX_GROUP_MERGES",
]
