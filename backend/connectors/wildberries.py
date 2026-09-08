import aiohttp
from typing import Dict
import logging
from services.category_mapper import CategoryMapper

logger = logging.getLogger(__name__)

class WildberriesConnector:
    """Интеграция с Wildberries Seller API"""
    
    def __init__(self, api_key: str, use_mock: bool = False):
        self.api_key = api_key
        self.base_url = "https://suppliers-api.wildberries.ru"
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }
        self.use_mock = use_mock
        self.category_mapper = CategoryMapper()  # ← Добавляем маппер
    
    async def create_product(self, product_data: Dict) -> Dict:
        """Создание товара на WB с правильным маппингом категорий"""
        if self.use_mock:
            return self._mock_create_product(product_data)
        
        # 1. Определяем категорию WB
        ozon_category_id = product_data.get("ozon_category_id")
        ozon_category_name = product_data.get("category", "")
        
        if ozon_category_id:
            wb_category = self.category_mapper.map_ozon_to_wildberries(ozon_category_id)
        else:
            wb_category = self.category_mapper.auto_map_by_text(ozon_category_name, "wildberries")
        
        logger.info(f"️ Маппинг категории: '{ozon_category_name}' → WB '{wb_category['name']}' (ID: {wb_category['id']})")
        
        # 2. Формируем payload
        payload = {
            "cards": [{
                "subjectID": wb_category["id"],  # ← Правильный ID категории!
                "title": product_data.get("name", "Без названия"),
                "description": product_data.get("description", ""),
                "brand": product_data.get("brand", "MyBrand"),
                "vendorCode": product_data.get("offer_id", "UNKNOWN_SKU"),
                "sizes": [{
                    "techSize": "ONE_SIZE",
                    "price": int(product_data.get("price", 0)),
                    "skus": [product_data.get("offer_id", "UNKNOWN_SKU")]
                }],
                "photos": product_data.get("photos", [])
            }]
        }
        
        # 3. Отправляем запрос
        url = f"{self.base_url}/content/v2/cards/create"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        return {"success": True, "data": data, "category": wb_category}
                    else:
                        error_text = await resp.text()
                        logger.error(f"WB API error ({resp.status}): {error_text}")
                        return {"success": False, "error": error_text}
        except Exception as e:
            logger.error(f"Error creating product on WB: {e}")
            return {"success": False, "error": str(e)}
    
    def _mock_create_product(self, product_data: Dict) -> Dict:
        """Mock-создание с маппингом категории"""
        ozon_category_name = product_data.get("category", "")
        wb_category = self.category_mapper.auto_map_by_text(ozon_category_name, "wildberries")
        
        logger.info(f" [MOCK] Категория: '{ozon_category_name}' → WB '{wb_category['name']}' (ID: {wb_category['id']})")
        logger.info(f"🎭 [MOCK] Товар '{product_data.get('name')}' создан на Wildberries!")
        
        return {
            "success": True,
            "data": {
                "message": "Товар успешно добавлен в черновики",
                "vendorCode": product_data.get("offer_id"),
                "wb_id": 99999999,
                "category": wb_category
            }
        }