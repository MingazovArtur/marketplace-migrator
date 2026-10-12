"""
Коннектор для Business API Яндекс Маркета (для продавцов)
Docs: https://yandex.ru/dev/market/partner-api/doc/ru/concepts/api-key
"""

import logging

import aiohttp

logger = logging.getLogger(__name__)


class YandexSellerConnector:
    """
    Интеграция с Business API Яндекс Маркета для получения собственных товаров.
    """

    BASE_URL = "https://api.partner.market.yandex.ru/v2"

    def __init__(self, campaign_id: str, oauth_token: str):
        """
        Args:
            campaign_id: ID вашего магазина (кампании) в Яндекс Маркете
            oauth_token: OAuth-токен из кабинета Яндекс Партнера/Продавца
        """
        self.campaign_id = campaign_id
        self.oauth_token = oauth_token
        self.headers = {"Authorization": f"OAuth {oauth_token}", "Content-Type": "application/json"}

    async def get_products(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Получает список товаров (offers) из вашего магазина на Яндекс Маркете.
        Docs: https://yandex.ru/dev/market/partner-api/doc/ru/reference/campaigns/getCampaignOffers
        """
        url = f"{self.BASE_URL}/campaigns/{self.campaign_id}/offers"
        params = {"limit": limit, "offset": offset}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Структура ответа: {"result": {"offers": [...], "paging": {...}}}
                        return data.get("result", {}).get("offers", [])
                    elif resp.status == 401:
                        raise ValueError("Ошибка авторизации: неверный OAuth-токен")
                    elif resp.status == 403:
                        raise ValueError(
                            "Доступ запрещен: проверьте права доступа к API для этого магазина"
                        )
                    elif resp.status == 404:
                        raise ValueError(f"Магазин с campaignId={self.campaign_id} не найден")
                    else:
                        error_text = await resp.text()
                        raise ValueError(f"HTTP ошибка {resp.status}: {error_text}")
        except aiohttp.ClientError as e:
            raise ValueError(f"Ошибка сети при запросе к Яндекс Маркету: {e}")

    def parse_yandex_offer(self, offer: dict) -> dict:
        """
        Преобразует формат offer из API Яндекса в наш универсальный формат Product
        """
        # Получаем цену
        price = 0.0
        if "price" in offer and "value" in offer["price"]:
            price = float(offer["price"]["value"])

        # Получаем фото (если есть в feed или content)
        photos = []
        # Примечание: полный URL фото часто нужно формировать или брать из вложенных структур,
        # но базовый offers endpoint может давать только pictureId.
        # Для простоты оставим заглушку или извлечем, если есть полный URL.
        if "pictures" in offer:
            photos = [pic.get("url", "") for pic in offer["pictures"] if pic.get("url")]

        return {
            "external_id": str(offer.get("offerId", "")),
            "offer_id": str(offer.get("offerId", "")),  # В Яндексе offerId = артикул продавца
            "name": offer.get("name", "Без названия"),
            "description": offer.get("description", ""),
            "price": price,
            "currency": offer.get("price", {}).get("currencyId", "RUR"),
            "category": "Категория Яндекса",  # Детали категории требуют отдельного запроса к models
            "photos": photos[:5],
            "available": offer.get("availability", "AVAILABLE") == "AVAILABLE",
            "source": "yandex_seller_api",
        }
