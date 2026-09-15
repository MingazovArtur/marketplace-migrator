"""
Роутер для работы со справочниками категорий и маппингом
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.session import SessionLocal
from services.category_service import category_service

router = APIRouter(prefix="/api", tags=["Categories"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/categories/{platform}")
def get_categories(platform: str, force_refresh: bool = False):
    """Получить список категорий для платформы"""
    categories = category_service.get_categories(platform, force_refresh)
    return {"success": True, "categories": categories, "total": len(categories)}


@router.get("/categories/{platform}/tree")
def get_categories_tree(platform: str):
    """Получить категории в виде дерева"""
    categories = category_service.get_categories(platform)
    
    # Строим дерево
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
    user_id: int = None  # В реальном приложении берется из JWT
):
    """Найти маппинг категории"""
    mapping = category_service.get_category_mapping(
        source_platform, source_category_id, target_platform, user_id
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
    user_id: int = 1  # В реальном приложении берется из JWT
):
    """Сохранить маппинг категории"""
    result = category_service.save_category_mapping(
        user_id, source_platform, source_category_id, 
        target_platform, target_category_id
    )
    
    if result["success"]:
        return result
    
    raise HTTPException(status_code=500, detail=result["error"])
@router.post("/categories/{platform}/refresh")
def refresh_categories_with_api(platform: str, api_key: str):
    """Обновить справочник категорий с использованием API ключа"""
    categories = category_service.get_categories_with_api_key(platform, api_key)
    return {
        "success": True, 
        "categories": categories, 
        "total": len(categories),
        "source": "api" if api_key else "mock"
    }