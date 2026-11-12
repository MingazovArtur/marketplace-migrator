"""
Справочники категорий площадок: список, дерево, обновление по API-ключу.

Вынесено без изменений из монолита routers/categories.py (Р7).
"""

import logging

from fastapi import APIRouter, Body, Depends, Query

from core.auth import get_current_user
from database.models import User
from routers.categories._support import RefreshCategoriesPayload
from services import cache_service
from services.category_service import category_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/categories/{platform}")
def get_categories(platform: str, force_refresh: bool = False):
    """
    Получить список категорий для платформы.
    КЭШИРУЕТСЯ на 2 часа, если не запрошен force_refresh.
    """
    cache_key = f"categories:{platform}:list"

    if not force_refresh:
        cached = cache_service.get(cache_key)
        if cached is not None:
            return {"success": True, "categories": cached, "total": len(cached), "from_cache": True}

    categories = category_service.get_categories(platform, force_refresh)
    cache_service.set(cache_key, categories, ttl=7200)

    return {
        "success": True,
        "categories": categories,
        "total": len(categories),
        "from_cache": False,
    }


@router.get("/categories/{platform}/tree")
def get_categories_tree(platform: str):
    """Получить категории в виде дерева"""
    categories = category_service.get_categories(platform)

    tree = []
    category_map = {cat["id"]: {**cat, "children": []} for cat in categories}

    for cat in categories:
        if cat["parent_id"] and cat["parent_id"] in category_map:
            category_map[cat["parent_id"]]["children"].append(category_map[cat["id"]])
        elif not cat["parent_id"]:
            tree.append(category_map[cat["id"]])

    return {"success": True, "tree": tree}


@router.post("/categories/{platform}/refresh")
def refresh_categories_with_api(
    platform: str,
    api_key: str | None = Query(default=None),
    payload: RefreshCategoriesPayload | None = Body(default=None),
    current_user: User = Depends(get_current_user),
):
    """
    ✅ ИСПРАВЛЕНО: Обновить справочник категорий с использованием API ключа.
    Принимает api_key как из JSON-тела (от CategoryMapping.jsx), так и из query-параметра.
    """
    resolved_key = (api_key or (payload.api_key if payload else "") or "").strip()
    categories = category_service.get_categories_with_api_key(platform, resolved_key)

    cache_service.delete_pattern(f"categories:{platform}:*")

    return {
        "success": True,
        "categories": categories,
        "total": len(categories),
        "source": "api" if resolved_key else "mock",
    }
