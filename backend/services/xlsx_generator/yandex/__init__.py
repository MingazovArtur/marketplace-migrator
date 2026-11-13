"""
Билдер книги Яндекс Маркета (лист «Список товаров» + инструкция).

Р23 (разбиение монолита services/xlsx_generator/yandex.py, 362 строки, на
под-пакет внутри пакета xlsx_generator — по прецедентам aliexpress/ (Р18)
и columns/ (Р19)):

  - _values.py      — определение категории (_guess_yandex_category,
                      17 правил по ключевым словам имени) и значения
                      ячеек шаблона (_yandex_cell_value: SKU/фото/описание/
                      штрихкод-EAN13/габариты/характеристики)
  - _instruction.py — 1-й лист «Инструкция» точно по образцу Яндекс
                      Маркета (3 шага загрузки, статусы проверки)
  - _book.py        — build_yandex_workbook: резервный генератор книги с
                      2 листами, если эталонный шаблон не загружен

Мёртвый хвостовой комментарий «===== Сборка книги Ozon =====» монолита
(артефакт истории, ниже кода не было) при разбиении удалён.

Публичный API сохранён: `from services.xlsx_generator.yandex import
build_yandex_workbook` (единственный импортёр —
services/xlsx_generator/__init__.py, точка использования — резервная
ветка платформы yandex в generate_export, когда эталонный шаблон
has_official_template ещё не загружен) — не менялся.
"""

from services.xlsx_generator.yandex._book import build_yandex_workbook
from services.xlsx_generator.yandex._instruction import _populate_yandex_instruction_sheet
from services.xlsx_generator.yandex._values import _guess_yandex_category, _yandex_cell_value

__all__ = [
    "build_yandex_workbook",
    "_guess_yandex_category",
    "_yandex_cell_value",
    "_populate_yandex_instruction_sheet",
]
