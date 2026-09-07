import aiohttp
from typing import List, Dict, Optional

class WildberriesConnector:
    """Интеграция с Wildberries API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://suppliers-api.wildberries.ru"
        self.headers = {"Authorization": api_key}
    
    async def get_products(self) -> List[Dict]:
        """Получить список товаров"""
        url = f"{self.base_url}/content/v2/get/cards/list"
        payload = {
            "settings": {
                "cursor": {"limit": 100},
                "filter": {}
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                data = await resp.json()
                return data.get("cards", [])
    
    async def create_product(self, product_data: Dict) -> Dict:
        """Создать товар"""
        url = f"{self.base_url}/content/v2/cards/create"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=product_data) as resp:
                return await resp.json()