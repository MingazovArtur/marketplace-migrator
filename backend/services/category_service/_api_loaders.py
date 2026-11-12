"""Загрузка категорий из реальных API площадок (Ozon, WB, Яндекс Маркет).

Чистые функции без состояния; при ошибке возвращают None (фолбэк на
встроенные справочники делает вызывающий).
Вынесено без изменений из монолита services/category_service.py (Р6).
"""

import logging

import httpx

logger = logging.getLogger(__name__)


def load_categories_from_api(platform: str, api_key: str) -> list[dict] | None:
    """
    Загрузка реальных категорий из API площадки.
    Возвращает None при ошибке.
    """
    if not api_key:
        return None

    try:
        if platform == "ozon":
            return _load_ozon_categories(api_key)
        elif platform == "wildberries":
            return _load_wildberries_categories(api_key)
        elif platform == "yandex":
            return _load_yandex_categories(api_key)
    except Exception as e:
        logger.error(f"Ошибка загрузки категорий из API {platform}: {e}")
        return None

    return None


def _load_ozon_categories(api_key: str) -> list[dict] | None:
    """Загрузка категорий из Ozon Seller API"""
    client_id, api_key_val = api_key.split(":") if ":" in api_key else (api_key, api_key)

    response = httpx.post(
        "https://api-seller.ozon.ru/v1/description-category/tree",
        headers={
            "Client-Id": client_id,
            "Api-Key": api_key_val,
            "Content-Type": "application/json",
        },
        json={"language": "DEFAULT"},
        timeout=10,
    )

    if response.status_code == 200:
        raw = response.json().get("result", [])
        return [
            {
                "id": str(cat["id"]),
                "name": cat["name"],
                "parent_id": str(cat["parent_id"]) if cat.get("parent_id") else None,
                "full_path": None,
                "level": 0,
            }
            for cat in raw
            if not cat.get("disabled", False)
        ]

    logger.warning(f"Ozon API вернул статус {response.status_code}")
    return None


def _load_wildberries_categories(api_key: str) -> list[dict] | None:
    """Загрузка категорий из WB Content API"""
    response = httpx.get(
        "https://content.wildberries.ru/content/v2/object/all",
        headers={"Authorization": api_key},
        timeout=10,
    )

    if response.status_code == 200:
        raw = response.json()
        return [
            {
                "id": str(subj["subjectId"]),
                "name": subj["subjectName"],
                "parent_id": (
                    str(subj.get("parentSubjectId")) if subj.get("parentSubjectId") else None
                ),
                "full_path": None,
                "level": 0,
            }
            for subj in raw
        ]

    logger.warning(f"WB API вернул статус {response.status_code}")
    return None


def _load_yandex_categories(api_key: str) -> list[dict] | None:
    """Загрузка категорий из Yandex Business API"""
    token, campaign_id = api_key.split(":") if ":" in api_key else (api_key, "")

    response = httpx.get(
        "https://api.partner.market.yandex.ru/v2/categories",
        headers={"Authorization": f"OAuth {token}"},
        params={"campaignId": campaign_id},
        timeout=10,
    )

    if response.status_code == 200:
        raw = response.json().get("categories", [])
        return [
            {
                "id": str(cat["id"]),
                "name": cat["name"],
                "parent_id": str(cat["parentId"]) if cat.get("parentId") else None,
                "full_path": None,
                "level": 0,
            }
            for cat in raw
        ]

    logger.warning(f"Yandex API вернул статус {response.status_code}")
    return None
