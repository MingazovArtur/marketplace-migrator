"""
Мультиплатформенное хранилище и заполнение ЭТАЛОННЫХ шаблонов площадок
(Ozon, Яндекс Маркет, Wildberries, Магнит Маркет, Мегамаркет,
Холодильник.ру, AliExpress).

Пользователь скачивает официальный XLSX-шаблон в кабинете площадки и загружает
его в разделе «Шаблоны». При выгрузке мы открываем этот файл как КАРКАС:
все листы («Инструкция», «Список товаров», «Шаблон», скрытые словари), шапка,
стили, выпадающие списки и метаданные остаются 100% оригинальными — мы только
удаляем строку-пример и записываем товары в соответствующие столбцы.

✅ Если для площадки загружен хотя бы один шаблон (например, «Универсальный»),
   он автоматически используется для выгрузки всех товаров на эту площадку.

Р2 (разбиение монолита services/template_filler.py, 993 строки, на пакет —
по прецеденту tasks/, repository/, xlsx_generator/ из docs/engineering.md):

  - _common.py    — константы и чистые хелперы (нормализация, EAN-13, категории)
  - _sheet_scan.py — сканирование книги: лист данных, строка заголовков, строка данных
  - _storage.py    — index.json + файлы эталонов, поиск с умным фолбэком, CRUD
  - _values.py     — значения строки товара для 7 площадок, разворот вариаций
  - _filler.py     — fill_official_template (заполнение каркаса)

Публичный API сохранён без изменений: все имена, которые импортировались
из монолита (включая рабочие _norm/_row_values/_build_enum_fix/
_expand_products_for_platform для xlsx_generator), доступны отсюда.
"""

from services.template_filler._common import (
    BRAND_SYNONYMS,
    MARKING_SYNONYMS,
    MODEL_SYNONYMS,
    UNIVERSAL_NAMES,
    VAT_LABELS,
    _norm,
)
from services.template_filler._filler import fill_official_template
from services.template_filler._storage import (
    INDEX_PATH,
    TEMPLATES_DIR,
    delete_official_template,
    get_template_meta,
    has_official_template,
    list_official_templates,
    list_template_names,
    read_template_bytes,
    save_official_template,
    template_path,
    validate_template_bytes,
)
from services.template_filler._values import (
    _build_enum_fix,
    _expand_products_for_platform,
    _row_values,
)

__all__ = [
    # Публичный API хранилища
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
    # Приватные имена, используемые xlsx_generator (aliexpress/megamarket)
    "_build_enum_fix",
    "_expand_products_for_platform",
    "_norm",
    "_row_values",
    # Константы (для совместимости с монолитом)
    "TEMPLATES_DIR",
    "INDEX_PATH",
    "VAT_LABELS",
    "BRAND_SYNONYMS",
    "MODEL_SYNONYMS",
    "MARKING_SYNONYMS",
    "UNIVERSAL_NAMES",
]
