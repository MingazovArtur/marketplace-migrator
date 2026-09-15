"""
Роутер для работы со справочниками категорий и маппингом
"""
from fastapi import APIRouter, HTTPException, Depends
from services.category_service import category_service
from core.auth import get_current_user
from database.models import User

router = APIRouter(prefix="/api", tags=["Categories"])


@router.get("/categories/{platform}")
def get_categories(platform: str, force_refresh: bool = False):
    """Получить список категорий для платформы"""
    categories = category_service.get_categories(platform, force_refresh)
    return {"success": True, "categories": categories, "total": len(categories)}


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


@router.get("/category-mapping")
def get_category_mapping(
    source_platform: str,
    source_category_id: str,
    target_platform: str,
    current_user: User = Depends(get_current_user)  # ✅ Из JWT, не из параметров!
):
    """Найти маппинг категории для текущего пользователя"""
    mapping = category_service.get_category_mapping(
        source_platform, source_category_id, target_platform, current_user.id
    )
    
    if mapping:
        return {"success": True, "mapping": mapping}
    
    return {"success": False, "mapping": None}


@router.post("/category-mapping")
def save_category_mapping(
    source_platform: str,
    source_category_id: str,
    target_platform: str,
    target_category_id: str,
    current_user: User = Depends(get_current_user)  # ✅ Из JWT
):
    """Сохранить маппинг категории для текущего пользователя"""
    result = category_service.save_category_mapping(
        current_user.id,
        source_platform,
        source_category_id,
        target_platform,
        target_category_id
    )
    
    if result["success"]:
        return result
    
    raise HTTPException(status_code=500, detail=result["error"])


@router.post("/categories/{platform}/refresh")  # ✅ Убраны пробелы
def refresh_categories_with_api(
    platform: str,
    api_key: str,
    current_user: User = Depends(get_current_user)  # ✅ Добавлена авторизация
):
    """Обновить справочник категорий с использованием API ключа"""
    categories = category_service.get_categories_with_api_key(platform, api_key)
    return {
        "success": True,
        "categories": categories,
        "total": len(categories),
        "source": "api" if api_key else "mock"
    }