"""Реестр парсеров площадок (7 активных площадок).

Вынесено без изменений из монолита parsers/factory.py (Р25): подклассы
SmartMarketplaceParser с фиксированной площадкой и словарь PARSERS.
"""

from parsers.factory._smart import SmartMarketplaceParser
from parsers.magnit import MagnitFileParser
from parsers.ozon import OzonFileParser
from parsers.wildberries import WBFileParser
from parsers.yandex import YandexFileParser


class MegamarketFileParser(SmartMarketplaceParser):
    """Парсер файлов Мегамаркета (Excel-файл с ассортиментом)."""

    @property
    def platform(self) -> str:
        return "megamarket"


class HolodilnikFileParser(SmartMarketplaceParser):
    """Парсер файлов Холодильник.ру."""

    @property
    def platform(self) -> str:
        return "holodilnik"


class AliexpressFileParser(SmartMarketplaceParser):
    """Парсер файлов AliExpress (официальный XLSX-шаблон)."""

    @property
    def platform(self) -> str:
        return "aliexpress"


# Реестр парсеров (7 активных площадок)
PARSERS = {
    "ozon": OzonFileParser,
    "magnit": MagnitFileParser,
    "wildberries": WBFileParser,
    "yandex": YandexFileParser,
    "megamarket": MegamarketFileParser,
    "holodilnik": HolodilnikFileParser,
    "aliexpress": AliexpressFileParser,
}
