"""Дерево категорий Ozon: обход до листьев.

Для атрибутов нужна пара: description_category_id (родителя) + type_id (листа).
Вынесено без изменений из монолита services/ozon_specs.py (Р8).
"""

import asyncio
import logging

import httpx

from services.ozon_specs._http import _ozon_headers, _post

logger = logging.getLogger(__name__)


async def fetch_ozon_category_tree(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    client_id: str,
    api_key: str,
) -> list[dict]:
    """
    Плоский список ЛИСТЬЕВ дерева категорий Ozon.
    Для атрибутов нужна пара: description_category_id (родителя) + type_id (листа).
    """
    headers = _ozon_headers(client_id, api_key)
    data = await _post(
        client, sem, "/v1/description-category/tree", {"language": "DEFAULT"}, headers
    )
    result = data.get("result") or []

    leaves = []
    stats = {"total": 0, "leaves": 0, "skipped": 0}

    def walk(nodes, parent_cat_id=None, parent_cat_name=None):
        for node in nodes:
            stats["total"] += 1
            children = node.get("children") or []
            own_cat_id = node.get("description_category_id")
            own_cat_name = node.get("category_name")
            type_id = node.get("type_id")
            type_name = node.get("type_name")

            if children:
                walk(
                    children,
                    parent_cat_id=own_cat_id or parent_cat_id,
                    parent_cat_name=own_cat_name or parent_cat_name,
                )
                continue

            if not type_id or not type_name:
                stats["skipped"] += 1
                continue

            cat_id = parent_cat_id
            cat_name = parent_cat_name
            if not cat_id:
                stats["skipped"] += 1
                continue

            leaves.append(
                {
                    "id": str(cat_id),
                    "type_id": int(type_id),
                    "name": cat_name or "",
                    "type_name": type_name or "",
                    "parent_id": None,
                    "disabled": bool(node.get("disabled")),
                }
            )
            stats["leaves"] += 1

    walk(result)
    logger.info(
        f"🌳 Ozon tree: total={stats['total']}, leaves={stats['leaves']}, skipped={stats['skipped']}"
    )
    return [leaf for leaf in leaves if not leaf["disabled"]]
