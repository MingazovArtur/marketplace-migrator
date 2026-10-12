"""
Парсер YML-фидов Яндекс Маркета
Docs: https://yandex.ru/support/partner2/yml/yml-format.html
"""

import logging
import re
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

logger = logging.getLogger(__name__)


class YmlParser:
    """Парсер YML (Yandex Market Language) файлов"""

    # Пространства имён, которые могут встречаться в YML
    NAMESPACES = {"yml": "http://www.w3.org/1999/xhtml"}

    def __init__(self, max_offers: int = 50):
        """
        Args:
            max_offers: Максимальное количество товаров для импорта (защита от огромных фидов)
        """
        self.max_offers = max_offers

    def validate_url(self, url: str) -> bool:
        """Проверяет, что URL валидный и похож на YML-фид"""
        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                return False
            if result.scheme not in ("http", "https"):
                return False
            return True
        except Exception:
            return False

    def fetch_and_parse(self, url: str) -> dict:
        """
        Скачивает и парсит YML-фид
        Возвращает: {
            "shop_name": str,
            "categories": {id: name},
            "offers": [list of parsed products],
            "total_offers": int,
            "parsed_offers": int
        }
        """
        if not self.validate_url(url):
            raise ValueError(f"Невалидный URL: {url}")

        logger.info(f"📡 Скачиваем YML-фид: {url}")

        try:
            response = requests.get(
                url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Marketplace Migrator Bot)"}
            )
            response.raise_for_status()

            # Проверяем Content-Type
            content_type = response.headers.get("Content-Type", "").lower()
            if "xml" not in content_type and "text" not in content_type:
                logger.warning(f"⚠️  Нестандартный Content-Type: {content_type}, пробуем парсить")

            return self._parse_xml(response.content, url)

        except requests.exceptions.Timeout:
            raise ValueError("Таймаут при загрузке фида (лимит 30 секунд)")
        except requests.exceptions.ConnectionError:
            raise ValueError("Не удалось подключиться к серверу. Проверьте URL.")
        except requests.exceptions.HTTPError as e:
            raise ValueError(f"HTTP ошибка {e.response.status_code}: {url}")
        except ElementTree.ParseError as e:
            raise ValueError(f"Ошибка парсинга XML: {e}")

    def _parse_xml(self, content: bytes, source_url: str) -> dict:
        """Парсит XML-содержимое YML-фида"""
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as e:
            raise ValueError(f"Невалидный XML: {e}")

        # Находим корневой элемент (может быть с namespace или без)
        shop = root.find(".//shop")
        if shop is None:
            # Пробуем с namespace
            for ns_prefix in ["yml", ""]:
                shop = root.find(f'.//{{{self.NAMESPACES.get(ns_prefix, "")}}}shop')
                if shop is not None:
                    break

        if shop is None:
            raise ValueError("Не найден элемент <shop> в YML-фиде")

        # 1. Получаем название магазина
        shop_name_elem = shop.find("name")
        shop_name = shop_name_elem.text if shop_name_elem is not None else "Неизвестный магазин"

        # 2. Парсим категории
        categories = {}
        categories_elem = shop.find("categories")
        if categories_elem is not None:
            for cat in categories_elem.findall("category"):
                cat_id = cat.get("id")
                if cat_id and cat.text:
                    categories[cat_id] = cat.text.strip()

        # 3. Парсим товары (offers)
        offers_elem = shop.find("offers")
        if offers_elem is None:
            raise ValueError("Не найден элемент <offers> в YML-фиде")

        all_offers = offers_elem.findall("offer")
        total_offers = len(all_offers)

        # Ограничиваем количество для демо
        parsed_offers = []
        for offer in all_offers[: self.max_offers]:
            parsed = self._parse_offer(offer, categories)
            if parsed:
                parsed_offers.append(parsed)

        logger.info(f"✅ Распарсено {len(parsed_offers)}/{total_offers} товаров из {shop_name}")

        return {
            "shop_name": shop_name,
            "categories": categories,
            "offers": parsed_offers,
            "total_offers": total_offers,
            "parsed_offers": len(parsed_offers),
            "source_url": source_url,
        }

    def _parse_offer(self, offer_elem, categories: dict) -> dict | None:
        """Парсит один элемент <offer>"""
        try:
            offer_id = offer_elem.get("id", "")
            available = offer_elem.get("available", "true").lower() == "true"

            if not available:
                return None  # Пропускаем недоступные товары

            # Базовые поля
            name_elem = offer_elem.find("name")
            name = (
                name_elem.text.strip()
                if name_elem is not None and name_elem.text
                else "Без названия"
            )

            price_elem = offer_elem.find("price")
            price = float(price_elem.text) if price_elem is not None and price_elem.text else 0.0

            currency_elem = offer_elem.find("currencyId")
            currency = currency_elem.text if currency_elem is not None else "RUR"

            # Описание
            description_elem = offer_elem.find("description")
            description = ""
            if description_elem is not None and description_elem.text:
                # Убираем HTML-теги из описания
                description = re.sub(r"<[^>]+>", " ", description_elem.text).strip()
                description = description[:500]  # Ограничиваем длину

            # Фотографии
            pictures = []
            for pic_elem in offer_elem.findall("picture"):
                if pic_elem.text:
                    pictures.append(pic_elem.text.strip())

            # Категория
            category_id = ""
            category_name = "Без категории"
            cat_elem = offer_elem.find("categoryId")
            if cat_elem is not None and cat_elem.text:
                category_id = cat_elem.text.strip()
                category_name = categories.get(category_id, "Без категории")

            # Артикул (vendorCode)
            vendor_code_elem = offer_elem.find("vendorCode")
            vendor_code = (
                vendor_code_elem.text.strip()
                if vendor_code_elem is not None and vendor_code_elem.text
                else f"YML-{offer_id}"
            )

            # Бренд
            vendor_elem = offer_elem.find("vendor")
            vendor = (
                vendor_elem.text.strip() if vendor_elem is not None and vendor_elem.text else ""
            )

            # Параметры (характеристики)
            params = {}
            for param_elem in offer_elem.findall("param"):
                param_name = param_elem.get("name", "")
                if param_name and param_elem.text:
                    params[param_name] = param_elem.text.strip()

            return {
                "external_id": offer_id,
                "offer_id": vendor_code,
                "name": name,
                "description": description,
                "price": price,
                "currency": currency,
                "category_id": category_id,
                "category": category_name,
                "photos": pictures[:5],  # Берём максимум 5 фото
                "vendor": vendor,
                "params": params,
                "available": available,
                "source": "yandex_yml",
            }

        except Exception as e:
            logger.warning(f"⚠️  Ошибка парсинга offer {offer_elem.get('id')}: {e}")
            return None


def parse_yml_url(url: str, max_offers: int = 50) -> list[dict]:
    """Удобная обёртка для роутеров: список товаров из YML-фида."""
    parser = YmlParser(max_offers=max_offers)
    result = parser.fetch_and_parse(url)
    return result["offers"]
