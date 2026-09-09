from enum import Enum
from typing import Dict, Type

class Platform(str, Enum):
    """Все поддерживаемые маркетплейсы"""
    OZON = "ozon"
    WILDBERRIES = "wildberries"
    YANDEX = "yandex"
    
    @classmethod
    def display_name(cls, platform: str) -> str:
        """Человекочитаемое название"""
        names = {
            cls.OZON: "Ozon",
            cls.WILDBERRIES: "Wildberries",
            cls.YANDEX: "Яндекс Маркет"
        }
        return names.get(platform, platform)
    
    @classmethod
    def all_values(cls) -> list:
        """Список всех значений для UI"""
        return [p.value for p in cls]


# Конфигурация каждой платформы
PLATFORM_CONFIG: Dict[str, Dict] = {
    Platform.OZON: {
        "name": "Ozon",
        "auth_format": "CLIENT_ID:API_KEY",
        "auth_hint": "Берется в настройках Ozon Seller → API ключи",
        "mock_key": "test:test",
        "color": "#005bff"
    },
    Platform.WILDBERRIES: {
        "name": "Wildberries",
        "auth_format": "API_KEY",
        "auth_hint": "Берется в настройках WB Seller → Доступ к API",
        "mock_key": "mock_wb_key",
        "color": "#cb11ab"
    },
    Platform.YANDEX: {
        "name": "Яндекс Маркет",
        "auth_format": "CLIENT_ID:TOKEN",
        "auth_hint": "Берется в кабинете Яндекс Маркет Партнер",
        "mock_key": "test:test",
        "color": "#fc3f1d"
    }
}