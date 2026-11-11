"""
Парсер YML-фидов Яндекс Маркета с защитой от SSRF и XML Bomb (XXE).
Docs: https://yandex.ru/support/partner2/yml/yml-format.html
"""

import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

MAX_YML_SIZE_BYTES = 25 * 1024 * 1024  # 25 МБ — защита от переполнения памяти


class YmlParser:
    """Парсер YML (Yandex Market Language) файлов"""

    NAMESPACES = {"yml": "http://www.w3.org/1999/xhtml"}

    def __init__(self, max_offers: int = 50):
        """
        Args:
            max_offers: Максимальное количество товаров для импорта (защита от огромных фидов)
        """
        self.max_offers = max_offers

    def validate_url(self, url: str) -> bool:
        """
        Проверяет, что URL валидный, использует http/https и НЕ ведёт
        во внутреннюю сеть (защита от SSRF).
        """
        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                return False
            if result.scheme not in ("http", "https"):
                return False

            hostname = result.hostname
            if not hostname:
                return False

            # Запрещаем очевидные локальные имена внутри Docker-сети
            forbidden_hosts = {"localhost", "db", "redis", "backend", "celery", "nginx"}
            if hostname.lower() in forbidden_hosts:
                logger.warning(f"🚫 SSRF block: запрещённый хост {hostname}")
                return False

            # Резолвим все IP-адреса хоста и проверяем, что среди них нет приватных/локальных
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if (
                    ip_obj.is_private
                    or ip_obj.is_loopback
                    or ip_obj.is_link_local
                    or ip_obj.is_multicast
                    or ip_obj.is_reserved
                ):
                    logger.warning(f"🚫 SSRF block: хост {hostname} резолвится во внутренний IP {ip_str}")
                    return False

            return True
        except Exception as e:
            logger.warning(f"Ошибка валидации URL {url}: {e}")
            return False

    def fetch_and_parse(self, url: str) -> dict:
        """
        Скачивает и парсит YML-фид.
        Возвращает: {
            "shop_name": str,
            "categories": {id: name},
            "offers": [list of parsed products],
            "total_offers": int,
            "parsed_offers": int
        }
        """
        if not self.validate_url(url):
            raise ValueError(
                f"Невалидный или небезопасный URL: {url}. "
                "Разрешены только публичные http/https адреса."
            )

        logger.info(f"📡 Скачиваем YML-фид: {url}")

        try:
            with httpx.Client(
                timeout=30,
                # follow_redirects по умолчанию выключен — защита от SSRF-редиректа на внутренний IP
                headers={"User-Agent": "Mozilla/5.0 (Marketplace Migrator Bot)"},
            ) as client:
                with client.stream("GET", url) as response:
                    if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                        redirect_url = response.headers.get("Location", "")
                        if not self.validate_url(redirect_url):
                            raise ValueError("Редирект фида ведёт на недопустимый адрес")
                        return self.fetch_and_parse(redirect_url)

                    response.raise_for_status()

                    content_type = response.headers.get("Content-Type", "").lower()
                    if "xml" not in content_type and "text" not in content_type:
                        logger.warning(
                            f"⚠️ Нестандартный Content-Type: {content_type}, пробуем парсить"
                        )

                    chunks = []
                    total_bytes = 0
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        total_bytes += len(chunk)
                        if total_bytes > MAX_YML_SIZE_BYTES:
                            raise ValueError("Размер YML-фида превышает допустимый лимит (25 МБ)")
                        chunks.append(chunk)

                    content = b"".join(chunks)

            return self._parse_xml(content, url)

        except httpx.TimeoutException:
            raise ValueError("Таймаут при загрузке фида (лимит 30 секунд)")
        except httpx.TransportError:
            raise ValueError("Не удалось подключиться к серверу. Проверьте URL.")
        except httpx.HTTPStatusError as e:
            raise ValueError(f"HTTP ошибка {e.response.status_code}: {url}")
        except ElementTree.ParseError as e:
            raise ValueError(f"Ошибка парсинга XML: {e}")

    def _parse_xml(self, content: bytes, source_url: str) -> dict:
        """Парсит XML-содержимое YML-фида с защитой от XML Bomb (ENTITY)."""
        # Защита от Billion Laughs / XXE: запрещаем объявления <!ENTITY в XML
        head_sample = content[:4096].upper()
        if b"<!ENTITY" in head_sample:
            raise ValueError("XML содержит запрещённые конструкции <!ENTITY> (защита от XXE/XML Bomb)")

        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as e:
            raise ValueError(f"Невалидный XML: {e}")

        shop = root.find(".//shop")
        if shop is None:
            for ns_prefix in ["yml", ""]:
                shop = root.find(f'.//{{{self.NAMESPACES.get(ns_prefix, "")}}}shop')
                if shop is not None:
                    break

        if shop is None:
            raise ValueError("Не найден элемент <shop> в YML-фиде")

        shop_name_elem = shop.find("name")
        shop_name = (
            shop_name_elem.text.strip()
            if shop_name_elem is not None and shop_name_elem.text
            else "Неизвестный магазин"
        )

        categories = {}
        categories_elem = shop.find("categories")
        if categories_elem is not None:
            for cat in categories_elem.findall("category"):
                cat_id = cat.get("id")
                if cat_id and cat.text:
                    categories[cat_id] = cat.text.strip()

        offers_elem = shop.find("offers")
        if offers_elem is None:
            raise ValueError("Не найден элемент <offers> в YML-фиде")

        all_offers = offers_elem.findall("offer")
        total_offers = len(all_offers)

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
                return None

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

            description_elem = offer_elem.find("description")
            description = ""
            if description_elem is not None and description_elem.text:
                description = re.sub(r"<[^>]+>", " ", description_elem.text).strip()
                description = description[:500]

            pictures = []
            for pic_elem in offer_elem.findall("picture"):
                if pic_elem.text:
                    pictures.append(pic_elem.text.strip())

            category_id = ""
            category_name = "Без категории"
            cat_elem = offer_elem.find("categoryId")
            if cat_elem is not None and cat_elem.text:
                category_id = cat_elem.text.strip()
                category_name = categories.get(category_id, "Без категории")

            vendor_code_elem = offer_elem.find("vendorCode")
            vendor_code = (
                vendor_code_elem.text.strip()
                if vendor_code_elem is not None and vendor_code_elem.text
                else f"YML-{offer_id}"
            )

            vendor_elem = offer_elem.find("vendor")
            vendor = (
                vendor_elem.text.strip() if vendor_elem is not None and vendor_elem.text else ""
            )

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
                "photos": pictures[:5],
                "vendor": vendor,
                "params": params,
                "available": available,
                "source": "yandex_yml",
            }

        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга offer {offer_elem.get('id')}: {e}")
            return None


def parse_yml_url(url: str, max_offers: int = 50) -> list[dict]:
    """Удобная обёртка для роутеров: список товаров из YML-фида."""
    parser = YmlParser(max_offers=max_offers)
    result = parser.fetch_and_parse(url)
    return result["offers"]