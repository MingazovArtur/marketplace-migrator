"""
Парсер файлов Яндекс Маркета (официальный XLSX-шаблон со строками групп/подсказок/примера + плоские CSV/XLSX).

Р24 (разбиение монолита parsers/yandex.py, 342 строки, на пакет — по
прецедентам Р8–Р23 из docs/engineering.md):

  - _support.py — маркеры служебных строк шаблона (YANDEX_SKIP_MARKERS,
                  строки 3-4: подсказки и пример Makita), конвертеры
                  единиц (_cm_to_mm, _kg_to_grams), парсер колонки
                  «Характеристики товара» (_parse_yandex_characteristics)
  - _parser.py  — класс YandexFileParser: поиск листа и строки заголовков,
                  карта колонок шаблона (точное совпадение без «*» →
                  частичное), плоский CSV через find_column

Публичный API сохранён: `from parsers.yandex import YandexFileParser`
(единственный импортёр — parsers/factory: реестр PARSERS) — не менялся;
`from .yandex import YandexFileParser` в factory продолжит работать
(импортёры пакета отдают те же объекты, что подмодули).
"""

from parsers.yandex._parser import YandexFileParser
from parsers.yandex._support import (
    YANDEX_SKIP_MARKERS,
    _cm_to_mm,
    _kg_to_grams,
    _parse_yandex_characteristics,
)

__all__ = [
    "YandexFileParser",
    "YANDEX_SKIP_MARKERS",
    "_cm_to_mm",
    "_kg_to_grams",
    "_parse_yandex_characteristics",
]
