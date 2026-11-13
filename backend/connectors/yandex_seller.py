"""
Коннектор для Business API Яндекс Маркета (получение и выгрузка карточек товаров бизнеса).
Актуальный метод чтения каталога: POST /businesses/{businessId}/offer-mappings
"""

import logging

import httpx

logger = logging.getLogger(__name__)


def _build_ym_headers(token: str) -> dict[str, str]:
    """
    Формирует заголовки авторизации Яндекс Маркета:
    - Новые токены (ACMA:...) передаются в заголовке 'Api-Key'
    - Старые OAuth-токены (y0_...) — в 'Authorization: OAuth <token>'
    """
    clean = (token or "").strip()
    if clean.lower().startswith("oauth "):
        clean = clean[6:].strip()
        return {
            "Authorization": f"OAuth {clean}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    if clean.startswith("y0_"):
        return {
            "Authorization": f"OAuth {clean}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    return {
        "Api-Key": clean,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


class YandexSellerConnector:
    """
    Интеграция с Business API Яндекс Маркета для получения товаров каталога по businessId.
    """

    BASE_URL = "https://api.partner.market.yandex.ru"

    def __init__(self, business_id: str, api_token: str):
        self.business_id = str(business_id or "").strip()
        self.api_token = api_token.strip()
        self.headers = _build_ym_headers(self.api_token)

    async def get_products(self, limit: int = 100) -> list[dict]:
        """
        Получает список карточек товаров (offerMappings) из каталога бизнеса на Яндекс Маркете.
        Метод: POST /businesses/{businessId}/offer-mappings
        """
        url = f"{self.BASE_URL}/businesses/{self.business_id}/offer-mappings"
        params = {"limit": min(max(1, limit), 200)}
        payload: dict = {}

        # Принудительно используем IPv4, чтобы избежать [Errno 101] Network is unreachable в Docker
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")

        try:
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.post(
                    url, headers=self.headers, params=params, json=payload, timeout=20
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("result") or {}
                    mappings = result.get("offerMappings") or result.get("offers") or []
                    return [self.parse_yandex_offer(item) for item in mappings]

                error_text = resp.text
                if "API_DISABLED" in error_text:
                    raise ValueError(
                        f"Яндекс Маркет вернул API_DISABLED для кабинета {self.business_id}: "
                        "в кабинете пока нет активного (подключённого) магазина. "
                        "Завершите настройку магазина в ЛК Яндекса или импортируйте товары через Excel-файл."
                    )
                if resp.status_code == 401:
                    raise ValueError("Ошибка авторизации Яндекс Маркета (401): неверный API-ключ")
                raise ValueError(
                    f"Ошибка API Яндекс Маркета ({resp.status_code}): {error_text[:250]}"
                )
        except httpx.HTTPError as e:
            raise ValueError(f"Ошибка сети при запросе к Яндекс Маркету: {e}") from e

    def parse_yandex_offer(self, item: dict) -> dict:
        """
        Преобразует элемент offerMapping из ответа Яндекс Маркета в формат карточки товара.
        """
        offer = item.get("offer") if "offer" in item else item
        mapping = item.get("mapping") or {}

        offer_id = str(offer.get("offerId") or "")
        name = offer.get("name") or "Без названия"
        description = offer.get("description") or ""
        brand = offer.get("vendor") or ""

        raw_pics = offer.get("pictures") or []
        photos: list[str] = []
        for p in raw_pics:
            if isinstance(p, str) and p.strip():
                photos.append(p.strip())
            elif isinstance(p, dict) and p.get("url"):
                photos.append(str(p["url"]).strip())

        barcodes = offer.get("barcodes") or []
        barcode_str = ", ".join(str(b).strip() for b in barcodes if str(b).strip())

        price = 0.0
        basic_price = offer.get("basicPrice") or offer.get("price") or {}
        if isinstance(basic_price, dict) and basic_price.get("value") is not None:
            try:
                price = float(basic_price["value"])
            except (TypeError, ValueError):
                price = 0.0

        wd = offer.get("weightDimensions") or {}
        weight_grams = int(round(float(wd["weight"]) * 1000)) if wd.get("weight") else None
        length_mm = int(round(float(wd["length"]) * 10)) if wd.get("length") else None
        width_mm = int(round(float(wd["width"]) * 10)) if wd.get("width") else None
        height_mm = int(round(float(wd["height"]) * 10)) if wd.get("height") else None

        okpd_code = None
        for cc in offer.get("commodityCodes") or []:
            if (
                isinstance(cc, dict)
                and cc.get("code")
                and cc.get("type") in ("CUSTOMS_COMMODITY_CODE", None)
            ):
                okpd_code = str(cc["code"]).strip()
                break

        category_name = (
            mapping.get("marketCategoryName")
            or offer.get("category")
            or "Не указана"
        )
        market_sku = mapping.get("marketSku")

        return {
            "external_id": str(market_sku or offer_id),
            "sku": offer_id,
            "name": name,
            "description": description,
            "price": price,
            "category": category_name,
            "brand": brand,
            "barcode": barcode_str,
            "photos": photos[:30],
            "package_weight_grams": weight_grams,
            "package_length_mm": length_mm,
            "package_width_mm": width_mm,
            "package_height_mm": height_mm,
            "okpd_code": okpd_code,
            "source": "Яндекс Маркет (API)",
        }
