import aiohttp
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class YandexMarketConnector:
    """Интеграция с Яндекс Маркетом (DSP API / Content API)"""
    
    def __init__(self, client_id: str, token: str, use_mock: bool = False):
        self.client_id = client_id
        self.token = token
        self.base_url = "https://api.partner.market.yandex.ru"
        self.headers = {
            "Authorization": f"OAuth {token}",
            "Content-Type": "application/json"
        }
        self.use_mock = use_mock

    async def get_products(self, limit: int = 20) -> List[Dict]:
        if self.use_mock:
            return self._get_mock_products()
        
        # Реальный endpoint Яндекса (требует настройки)
        url = f"{self.base_url}/v2/campaigns/{self.client_id}/offer-mappings"
        # ... реализация реального запроса ...
        return []

    def parse_yandex_product(self, yandex_product: Dict) -> Dict:
        """Преобразует ответ Яндекса в Универсальную модель"""
        offer = yandex_product.get("offer", {})
        return {
            "external_id": offer.get("offerId"),
            "name": offer.get("name", "Без названия"),
            "description": offer.get("description", ""),
            "price": float(offer.get("price", 0)),
            "category": offer.get("categoryId", "Общая категория"),
            "photos": offer.get("pictures", []),
            "source": "yandex"
        }

    def _get_mock_products(self) -> List[Dict]:
        """Тестовые данные Яндекс Маркета"""
        return [
            {
                "offer": {
                    "offerId": "YAN-TEA-001",
                    "name": "Чай черный байховый, 100 пакетиков",
                    "description": "<p>Классический черный чай для бодрости.</p>",
                    "price": 350.00,
                    "categoryId": "90766", # Категория Яндекса
                    "pictures": [
                        "https://example.com/tea1.jpg",
                        "https://example.com/tea2.jpg"
                    ]
                }
            },
            {
                "offer": {
                    "offerId": "YAN-LAMP-002",
                    "name": "Светильник настольный LED, регулируемый",
                    "description": "<p>Экономичная светодиодная лампа с 3 режимами яркости.</p>",
                    "price": 1290.00,
                    "categoryId": "90636",
                    "pictures": ["https://example.com/lamp1.jpg"]
                }
            }
        ]