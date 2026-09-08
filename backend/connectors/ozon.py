import aiohttp
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class OzonConnector:
    """Интеграция с Ozon Seller API (на основе docs.ozon.ru/api/seller/)"""
    
    def __init__(self, client_id: str, api_key: str, use_mock: bool = False):
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = "https://api-seller.ozon.ru"
        self.headers = {
            "Client-Id": client_id,
            "Api-Key": api_key,
            "Content-Type": "application/json"
        }
        self.use_mock = use_mock # Флаг для тестирования без реального аккаунта

    async def get_products(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        Получение списка товаров.
        Docs: https://docs.ozon.ru/api/seller/#operation/PostingAPI_ProductsListV3
        """
        if self.use_mock:
            return self._get_mock_products()

        url = f"{self.base_url}/v3/product/list"
        # ВАЖНО: явно запрашиваем картинки и остатки, иначе API их не вернет
        payload = {
            "limit": limit,
            "offset": offset,
            "with": {
                "discounted_stocks": True,
                "images": True,
                "videos": False
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result", {}).get("items", [])
                    else:
                        error_text = await resp.text()
                        logger.error(f"Ozon API error ({resp.status}): {error_text}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching products from Ozon: {e}")
            return []

    def parse_ozon_product(self, ozon_product: Dict) -> Dict:
        """
        Преобразует ответ Ozon API в наш унифицированный формат для миграции
        """
        # 1. Цена
        price = float(ozon_product.get("price", 0))
        old_price = float(ozon_product.get("price_before_discount", 0))
        
        # 2. Фотографии (извлекаем URL из поля 'name')
        photos = []
        if "primary_image" in ozon_product and ozon_product["primary_image"]:
            photos.append(ozon_product["primary_image"])
        
        for img in ozon_product.get("images", []):
            if isinstance(img, dict) and "name" in img:
                photos.append(img["name"])
            elif isinstance(img, str):
                photos.append(img)
        
        # 3. Остатки
        quantity = 0
        if "discounted_stocks" in ozon_product:
            quantity = ozon_product["discounted_stocks"].get("present", 0)
        
        # 4. Характеристики (атрибуты)
        characteristics = {}
        for attr in ozon_product.get("attributes", []):
            if "key" in attr and "value" in attr:
                characteristics[attr["key"]] = attr["value"]
        
        return {
            "external_id": ozon_product.get("product_id"),      # ID Ozon
            "offer_id": ozon_product.get("offer_id", ""),       # ВАЖНО: Артикул продавца (SKU)
            "name": ozon_product.get("name", "Без названия"),
            "description": ozon_product.get("description_html", ozon_product.get("description", "")),
            "price": price,
            "old_price": old_price,
            "quantity": quantity,
            "category": ozon_product.get("category_name", ""),
            "characteristics": characteristics,
            "photos": photos,
            "source": "ozon"
        }

    def _get_mock_products(self) -> List[Dict]:
        """
        Расширенная эмуляция Ozon API с тестовыми товарами
        """
        return [
            {
                "product_id": 2380925,
                "offer_id": "SHVABRA-10L-WHITE",
                "name": "Швабра с отжимом и ведром, самоочищающаяся, 2 насадки, 10 л",
                "description_html": "<p>Швабра с ведром с отжимом — удобное решение для уборки. Два отсека по 5 литров.</p>",
                "price": "899.10",
                "price_before_discount": "3255.00",
                "category_name": "Дом и сад / Уборка / Швабры",
                "primary_image": "https://cdn1.ozone.ru/s3/multimedia-1-s/wc1000/2380925_1.jpg",
                "images": [
                    {"name": "https://cdn1.ozone.ru/s3/multimedia-1-s/wc1000/2380925_2.jpg", "state": "processed"},
                    {"name": "https://cdn1.ozone.ru/s3/multimedia-1-s/wc1000/2380925_3.jpg", "state": "processed"}
                ],
                "discounted_stocks": {"present": 211, "reserved": 5},
                "attributes": [
                    {"key": "Цвет", "value": "Белый"},
                    {"key": "Тип насадки", "value": "Микрофибра"},
                    {"key": "Объем", "value": "10 л"}
                ]
            },
            {
                "product_id": 4968284,
                "offer_id": "BOWL-SET-4PCS",
                "name": "Салатники миски с крышкой пластиковые, набор 4 шт",
                "description_html": "<p>Набор пластиковых мисок с крышками. Можно в микроволновку.</p>",
                "price": "450.00",
                "price_before_discount": "750.00",
                "category_name": "Посуда / Миски",
                "primary_image": "https://cdn1.ozone.ru/s3/multimedia-2-s/wc1000/4968284_1.jpg",
                "images": [],
                "discounted_stocks": {"present": 87, "reserved": 0},
                "attributes": [
                    {"key": "Материал", "value": "Пластик"},
                    {"key": "Количество", "value": "4 шт"}
                ]
            },
            {
                "product_id": 1122334,
                "offer_id": "HEADPHONE-BT-BLK",
                "name": "Беспроводные наушники с кейсом, Bluetooth 5.0",
                "description_html": "<p>Качественный звук, шумоподавление, 20 часов работы.</p>",
                "price": "1990.00",
                "price_before_discount": "3990.00",
                "category_name": "Электроника / Наушники",
                "primary_image": "https://cdn1.ozone.ru/s3/multimedia-3-s/wc1000/1122334_1.jpg",
                "images": [
                    {"name": "https://cdn1.ozone.ru/s3/multimedia-3-s/wc1000/1122334_2.jpg", "state": "processed"}
                ],
                "discounted_stocks": {"present": 45, "reserved": 3},
                "attributes": [
                    {"key": "Цвет", "value": "Черный"},
                    {"key": "Bluetooth", "value": "5.0"}
                ]
            },
            {
                "product_id": 5566778,
                "offer_id": "TSHIRT-COTTON-M",
                "name": "Футболка мужская хлопковая, классический крой, M",
                "description_html": "<p>100% хлопок, не садится после стирки.</p>",
                "price": "690.00",
                "price_before_discount": "1200.00",
                "category_name": "Одежда / Мужская / Футболки",
                "primary_image": "https://cdn1.ozone.ru/s3/multimedia-4-s/wc1000/5566778_1.jpg",
                "images": [],
                "discounted_stocks": {"present": 150, "reserved": 10},
                "attributes": [
                    {"key": "Размер", "value": "M"},
                    {"key": "Состав", "value": "100% хлопок"}
                ]
            },
            {
                "product_id": 9988776,
                "offer_id": "BOOK-PYTHON-2026",
                "name": "Изучаем Python программирование, 3-е издание",
                "description_html": "<p>Полное руководство по Python для начинающих и продвинутых.</p>",
                "price": "1290.00",
                "price_before_discount": "1890.00",
                "category_name": "Книги / Программирование",
                "primary_image": "https://cdn1.ozone.ru/s3/multimedia-5-s/wc1000/9988776_1.jpg",
                "images": [
                    {"name": "https://cdn1.ozone.ru/s3/multimedia-5-s/wc1000/9988776_2.jpg", "state": "processed"}
                ],
                "discounted_stocks": {"present": 32, "reserved": 1},
                "attributes": [
                    {"key": "Автор", "value": "Иванов И.И."},
                    {"key": "Год", "value": "2026"}
                ]
            }
        ]