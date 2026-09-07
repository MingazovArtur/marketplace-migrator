import aiohttp
from typing import List, Dict, Optional

class OzonConnector:
    """Интеграция с Ozon API"""
    
    def __init__(self, client_id: str, api_key: str):
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = "https://api-seller.ozon.ru"
        self.headers = {
            "Client-Id": client_id,
            "Api-Key": api_key,
            "Content-Type": "application/json"
        }
    
    async def get_products(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Получить список товаров"""
        url = f"{self.base_url}/v3/product/list"
        payload = {
            "limit": limit,
            "offset": offset,
            "with": {
                "discounted_stocks": True,
                "images": True
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                data = await resp.json()
                return data.get("result", {}).get("items", [])
    
    async def get_product_info(self, product_id: str) -> Optional[Dict]:
        """Получить детальную информацию о товаре"""
        url = f"{self.base_url}/v2/product/info"
        payload = {"product_id": product_id}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                data = await resp.json()
                return data.get("result")
    
    async def create_product(self, product_data: Dict) -> Dict:
        """Создать новый товар"""
        url = f"{self.base_url}/v1/product/import"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=product_data) as resp:
                return await resp.json()