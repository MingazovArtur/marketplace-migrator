import logging
from typing import List, Dict
from services.yml_parser import YmlParser

logger = logging.getLogger(__name__)


class YandexMarketConnector:
    """
    Интеграция с Яндекс Маркетом.
    Поддерживает:
    - Импорт через YML-фиды (без регистрации)
    - Mock-режим для тестирования
    """
    
    def __init__(self, source: str = "", use_mock: bool = False):
        """
        Args:
            source: URL YML-фида или тестовый ключ
            use_mock: Флаг тестового режима
        """
        self.source = source
        self.use_mock = use_mock
        self.yml_parser = YmlParser(max_offers=50)
    
    async def get_products(self, limit: int = 50) -> List[Dict]:
        """Получает список товаров"""
        if self.use_mock:
            return self._get_mock_products()
        
        # Парсим YML-фид
        try:
            result = self.yml_parser.fetch_and_parse(self.source)
            return result["offers"]
        except ValueError as e:
            logger.error(f" Ошибка парсинга YML: {e}")
            raise
    
    def parse_yandex_product(self, yml_product: Dict) -> Dict:
        """
        Преобразует товар из YML в универсальный формат.
        YML-парсер уже возвращает нужный формат, поэтому просто возвращаем как есть.
        """
        return yml_product
    
    def _get_mock_products(self) -> List[Dict]:
        """Тестовые данные для демонстрации"""
        return [
            {
                "external_id": "YML-001",
                "offer_id": "YAN-TEA-001",
                "name": "Чай черный байховый, 100 пакетиков",
                "description": "Классический черный чай для бодрости. Индийский, крупнолистовой.",
                "price": 350.00,
                "currency": "RUR",
                "category_id": "90766",
                "category": "Продукты питания / Чай",
                "photos": ["https://example.com/tea1.jpg", "https://example.com/tea2.jpg"],
                "vendor": "Чайный дом",
                "params": {"Вес": "200г", "Страна": "Индия"},
                "available": True,
                "source": "yandex_yml"
            },
            {
                "external_id": "YML-002",
                "offer_id": "YAN-LAMP-002",
                "name": "Светильник настольный LED, регулируемый",
                "description": "Экономичная светодиодная лампа с 3 режимами яркости и регулировкой цвета.",
                "price": 1290.00,
                "currency": "RUR",
                "category_id": "90636",
                "category": "Товары для дома / Освещение",
                "photos": ["https://example.com/lamp1.jpg"],
                "vendor": "СветТех",
                "params": {"Мощность": "12Вт", "Цвет": "Белый"},
                "available": True,
                "source": "yandex_yml"
            },
            {
                "external_id": "YML-003",
                "offer_id": "YAN-BOOK-003",
                "name": "Книга 'Python для начинающих', 2026",
                "description": "Полное руководство по программированию на Python. 500 страниц, мягкая обложка.",
                "price": 890.00,
                "currency": "RUR",
                "category_id": "90638",
                "category": "Книги / Программирование",
                "photos": ["https://example.com/book1.jpg", "https://example.com/book2.jpg"],
                "vendor": "ТехКнига",
                "params": {"Автор": "Иванов И.И.", "Страниц": "500"},
                "available": True,
                "source": "yandex_yml"
            }
        ]