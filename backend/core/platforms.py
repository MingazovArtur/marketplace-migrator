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
}

PRICE_RULES = {
    "ozon": 1.0,
    "wildberries": 1.15,
    "yandex": 1.0,
    "magnit": 1.0,
}
