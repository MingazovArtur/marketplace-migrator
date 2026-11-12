"""Дерево категорий Яндекс Маркета (POST /categories/tree) → плоский список листьев."""

import asyncio
import logging

import httpx

from services.yandex_specs._http import _post_ym

logger = logging.getLogger(__name__)


async def fetch_yandex_categories_tree(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    headers: dict,
) -> list[dict]:
    """
    Загружает полное дерево категорий Яндекс Маркета (POST /categories/tree)
    и возвращает список ЛИСТОВЫХ категорий в формате:
      {'id': '91491', 'name': 'Мобильные телефоны', 'full_name': 'Электроника / Мобильные телефоны', 'parent_id': '...'}
    """
    data = await _post_ym(client, sem, "/categories/tree", {"language": "RU"}, headers)
    root = data.get("result") or {}

    leaves: list[dict] = []

    def walk(node: dict, parent_id: str | None = None, parent_name: str | None = None):
        cat_id = node.get("id")
        cat_name = (node.get("name") or "").strip()
        children = node.get("children") or []

        if children:
            for ch in children:
                walk(
                    ch,
                    parent_id=str(cat_id) if cat_id else parent_id,
                    parent_name=cat_name if cat_name and cat_name != "Все товары" else parent_name,
                )
            return

        if not cat_id or not cat_name:
            return

        full_name = f"{parent_name} / {cat_name}" if parent_name else cat_name
        leaves.append(
            {
                "id": str(cat_id),
                "name": cat_name,
                "full_name": full_name,
                "parent_id": parent_id,
            }
        )

    walk(root)
    logger.info(f"🌳 Яндекс Маркет: найдено {len(leaves)} листовых категорий")
    return leaves
