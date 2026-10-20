"""
Реестр поддерживаемых платформ.
ЕДИНСТВЕННОЕ место регистрации новой площадки (backend).
"""

from enum import Enum


class Platform(str, Enum):
    OZON = "ozon"
    WILDBERRIES = "wildberries"
    YANDEX = "yandex"
    MAGNIT = "magnit"
    MEGAMARKET = "megamarket"
    POIZON = "poizon"
    HOLODILNIK = "holodilnik"
    STRANA = "strana"
    UDS = "uds"

    @classmethod
    def all_values(cls):
        return [p.value for p in cls]


# ❗ БЕЗ ПРОБЕЛОВ В КЛЮЧАХ И ЗНАЧЕНИЯХ
PLATFORM_CONFIG = {
    "ozon": {
        "name": "Ozon",
        "color": "#005bff",
        "logo": "O",
        "import_methods": ["api", "file", "yml"],
    },
    "wildberries": {
        "name": "Wildberries",
        "color": "#cb11ab",
        "logo": "WB",
        "import_methods": ["api", "file"],
    },
    "yandex": {
        "name": "Яндекс Маркет",
        "color": "#fc3f1d",
        "logo": "Я",
        "import_methods": ["api", "file", "yml"],
    },
    "magnit": {
        "name": "Магнит Маркет",
        "color": "#e31235",
        "logo": "ММ",
        "import_methods": ["file"],
    },
    "megamarket": {
        "name": "Мегамаркет",
        "color": "#8b3ffd",
        "logo": "СММ",
        "import_methods": ["file", "yml"],
    },
    "poizon": {
        "name": "Poizon",
        "color": "#00c2b8",
        "logo": "PZ",
        "import_methods": ["file"],
    },
    "holodilnik": {
        "name": "Холодильник.ру",
        "color": "#0072bc",
        "logo": "ХЛ",
        "import_methods": ["file", "yml"],
    },
    "strana": {
        "name": "Страна.маркет",
        "color": "#10b981",
        "logo": "СМ",
        "import_methods": ["file", "yml"],
    },
    "uds": {
        "name": "UDS",
        "color": "#6366f1",
        "logo": "UDS",
        "import_methods": ["file"],
    },
}

PRICE_RULES = {
    "ozon": 1.0,
    "wildberries": 1.15,
    "yandex": 1.0,
    "magnit": 1.0,
    "megamarket": 1.0,
    "poizon": 1.0,
    "holodilnik": 1.0,
    "strana": 1.0,
    "uds": 1.0,
}