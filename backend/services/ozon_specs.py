"""
Загрузчик спецификаций категорий Ozon через официальный Seller API.

Эндпоинты:
- POST /v1/description-category/tree         → дерево категорий
- POST /v1/description-category/attribute    → атрибуты категории со словарями

Документация: https://docs.ozon.ru/api/seller/
"""
import hashlib
import json
import logging
from typing import Optional

import httpx

from database.models import PlatformCategorySpec
from database.session import SessionLocal

logger = logging.getLogger(__name__)

OZON_API_BASE = "https://api-seller.ozon.ru"


def _ozon_headers(api_key: str, client_id: str) -> dict:
    """Ozon требует Client-Id + Api-Key (не Bearer!)."""
    return {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json",
    }


def _parse_ozon_key(raw_key: str) -> tuple[str, str]:
    """
    Пользователь вводит ключ как 'client_id:api_key'. Разбираем.
    """
    if ":" not in raw_key:
        raise ValueError("Ключ Ozon должен быть в формате 'client_id:api_key'")
    client_id, api_key = raw_key.split(":", 1)
    return client_id.strip(), api_key.strip()


async def fetch_ozon_category_tree(client: httpx.AsyncClient, client_id: str, api_key: str) -> list[dict]:
    """Получить плоский список категорий с деревом родителей."""
    resp = await client.post(
        f"{OZON_API_BASE}/v1/description-category/tree",
        headers=_ozon_headers(api_key, client_id),
        json={"language": "DEFAULT"},
    )
    resp.raise_for_status()
    data = resp.json()

    flat = []

    def walk(nodes, parent_id=None):
        for node in nodes:
            flat.append({
                "id": str(node.get("description_category_id") or node.get("category_id")),
                "name": node.get("category_name") or node.get("name"),
                "parent_id": parent_id,
                "is_leaf": node.get("disabled", False) is False and not node.get("children"),
            })
            if node.get("children"):
                walk(node["children"], parent_id=str(node.get("description_category_id")))

    walk(data.get("result", []))
    return flat


async def fetch_ozon_attributes(
    client: httpx.AsyncClient,
    client_id: str,
    api_key: str,
    description_category_id: int,
    type_id: int = 0,
) -> list[dict]:
    """Получить атрибуты категории со словарями значений."""
    resp = await client.post(
        f"{OZON_API_BASE}/v1/description-category/attribute",
        headers=_ozon_headers(api_key, client_id),
        json={
            "description_category_id": description_category_id,
            "type_id": type_id,
            "language": "DEFAULT",
        },
    )
    resp.raise_for_status()
    data = resp.json()

    attributes = []
    for attr in data.get("result", []):
        attr_type = attr.get("type", "")
        dict_values = None
        if attr.get("dictionary_id"):
            dict_values = await _fetch_dictionary(client, client_id, api_key, attr["dictionary_id"])

        attributes.append({
            "id": str(attr.get("id")),
            "name": attr.get("name"),
            "type": _map_ozon_type(attr_type),
            "required": attr.get("is_required", False),
            "group": _map_ozon_group(attr.get("group_id")),
            "values": dict_values,
            "case_sensitive": attr.get("is_case_sensitive", True),
            "separator": ";",
            "unit": attr.get("unit"),
            "allow_unit_in_value": attr.get("is_dependent", False),
        })

    return attributes


async def _fetch_dictionary(client, client_id, api_key, dictionary_id: int, limit: int = 5000) -> Optional[list[str]]:
    """Словарь значений атрибута (цвет, размер и т.д.)."""
    try:
        resp = await client.post(
            f"{OZON_API_BASE}/v1/description-category/attribute/values",
            headers=_ozon_headers(api_key, client_id),
            json={
                "attribute_id": 0,
                "dictionary_id": dictionary_id,
                "language": "DEFAULT",
                "last_value_id": 0,
                "limit": limit,
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            return [item.get("value") for item in data.get("result", []) if item.get("value")]
    except Exception as e:
        logger.warning(f"Failed to fetch dictionary {dictionary_id}: {e}")
    return None


def _map_ozon_type(ozon_type: str) -> str:
    mapping = {
        "Integer": "number",
        "Decimal": "number",
        "String": "text",
        "URL": "text",
        "Boolean": "select",
    }
    # Ozon возвращает 'String' и для свободного текста, и для выбора —
    # различаем по наличию dictionary_id в fetch_ozon_attributes
    return mapping.get(ozon_type, "text")


def _map_ozon_group(group_id: Optional[int]) -> str:
    # Эмпирические group_id из документации Ozon:
    groups = {
        1: "common",      # одинаковые для всех вариантов
        2: "brand",       # бренд
        3: "variant",     # атрибуты вариантов (цвет, размер)
        4: "additional",  # дополнительные
        5: "fits_for",    # "для чего подходит"
    }
    return groups.get(group_id, "common")


async def refresh_ozon_specs(user_id: int, raw_api_key: str, category_ids: Optional[list[str]] = None) -> dict:
    """
    Главный метод: подтягивает дерево категорий + атрибуты каждой категории,
    сохраняет в БД как PlatformCategorySpec.
    """
    client_id, api_key = _parse_ozon_key(raw_api_key)

    async with httpx.AsyncClient(timeout=60) as client:
        tree = await fetch_ozon_category_tree(client, client_id, api_key)

        if category_ids:
            tree = [n for n in tree if n["id"] in category_ids]

        fetched = 0
        errors = []

        for node in tree:
            try:
                attrs = await fetch_ozon_attributes(
                    client, client_id, api_key,
                    description_category_id=int(node["id"])
                )

                spec_content = {
                    "sheets": ["Шаблон Поставщика", "Документация PDF"],
                    "required_fields": [a["name"] for a in attrs if a["required"]],
                    "attributes": attrs,
                    "validation_rules": _build_validation_rules(attrs),
                    "special_requirements": _build_special_requirements(),
                }

                _upsert_spec(
                    user_id=user_id,
                    platform="ozon",
                    category_id=node["id"],
                    category_name=node["name"],
                    parent_category_id=node["parent_id"],
                    spec=spec_content,
                )
                fetched += 1
            except Exception as e:
                errors.append({"category_id": node["id"], "error": str(e)})
                logger.warning(f"Failed to fetch attrs for {node['id']}: {e}")

    return {
        "platform": "ozon",
        "fetched": fetched,
        "errors": len(errors),
        "error_details": errors[:20],
    }


def _build_validation_rules(attrs: list[dict]) -> dict:
    rules = {
        "barcode": {"pattern": "^[0-9]{8,14}$", "separator": ";"},
        "vat_rate": {"enum": ["none", "10", "22"]},
        "price": {"min": 0.01},
        "units_per_item": {"min": 1, "type": "integer"},
    }
    for attr in attrs:
        if attr["values"]:
            rules[attr["id"]] = {
                "enum": attr["values"],
                "case_sensitive": attr["case_sensitive"],
                "separator": attr["separator"] if attr["type"] == "multiselect" else None,
            }
    return rules


def _build_special_requirements() -> dict:
    return {
        "okpd_required_for_tags": [
            "одежда", "обувь", "шубы", "парфюмерия", "духи", "туалетная вода",
            "лекарства", "шины", "покрышки", "фотоаппараты", "лампы-вспышки",
            "товары лёгкой промышленности",
        ],
        "excisable_tags": [
            "сахаросодержащие напитки", "моторные масла", "безалкогольное пиво",
        ],
    }


def _upsert_spec(user_id, platform, category_id, category_name, parent_category_id, spec):
    db = SessionLocal()
    try:
        existing = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.user_id == user_id,
                PlatformCategorySpec.platform == platform,
                PlatformCategorySpec.category_id == category_id,
            )
            .first()
        )
        version = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]

        if existing:
            existing.category_name = category_name
            existing.parent_category_id = parent_category_id
            existing.spec = spec
            existing.version = version
            from datetime import datetime
            existing.fetched_at = datetime.utcnow()
        else:
            db.add(PlatformCategorySpec(
                user_id=user_id,
                platform=platform,
                category_id=category_id,
                category_name=category_name,
                parent_category_id=parent_category_id,
                spec=spec,
                version=version,
            ))
        db.commit()
    finally:
        db.close()