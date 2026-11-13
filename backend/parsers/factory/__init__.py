"""
Фабрика парсеров файлов маркетплейсов.
Выбирает нужный парсер по названию площадки.

Р25 (разбиение монолита parsers/factory.py, 334 строки, на пакет — по
прецедентам Р8–Р24 из docs/engineering.md):

  - _smart.py    — нормализация заголовков (_norm_col) и
                   SmartMarketplaceParser: распознавание многострочных
                   шапок официальных шаблонов, подбор SKU/названия/цены
                   по нормализованным ключам (Мегамаркет, Холодильник.ру,
                   AliExpress)
  - _registry.py — подклассы-плейсхолдеры (Megamarket/Holodilnik/
                   Aliexpress — только platform) и реестр PARSERS
                   (7 активных площадок)
  - _api.py      — фасад: get_parser / parse_file / preview_file

Публичный API сохранён: `from parsers.factory import parse_file,
preview_file, get_parser` (единственный импортёр — parsers/__init__.py —
не менялся); реестр PARSERS и классы парсеров реэкспортированы теми же
объектами, что в подмодулях. `from parsers import ...` работает как раньше
(импортёры routers/import_router/_file_import.py и /_preview.py не менялись).
"""

from parsers.factory._api import get_parser, parse_file, preview_file
from parsers.factory._registry import (
    PARSERS,
    AliexpressFileParser,
    HolodilnikFileParser,
    MegamarketFileParser,
)
from parsers.factory._smart import SmartMarketplaceParser, _norm_col

__all__ = [
    "get_parser",
    "parse_file",
    "preview_file",
    "PARSERS",
    "SmartMarketplaceParser",
    "MegamarketFileParser",
    "HolodilnikFileParser",
    "AliexpressFileParser",
    "_norm_col",
]
