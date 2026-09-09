import logging
from fastapi import APIRouter, HTTPException
from database.repository import repo
from models.schemas import MigrateRequest
from services.category_mapper import CategoryMapper
from core.platforms import Platform, PLATFORM_CONFIG
from tasks import migrate_product_task # <-- Импортируем задачу Celery

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Migration"])
category_mapper = CategoryMapper()

@router.post("/migrate/preview")
async def preview_migration(request: MigrateRequest):
    product = repo.get_by_id(request.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    target = request.target_marketplace.lower()
    target_category = category_mapper.auto_map_by_text(product.get("category") or "Дом и сад", target)
    
    price_multiplier = 1.15 if target == Platform.WILDBERRIES else 1.0
    new_price = round(product.get("price", 0) * price_multiplier, 2)
    
    return {
        "success": True,
        "preview": {
            "original": {
                "name": product.get("name"),
                "price": product.get("price"),
                "category": product.get("category") or "Не указана"
            },
            "target": {
                "name": product.get("name"),
                "price": new_price,
                "category": target_category["name"],
                "category_id": target_category["id"]
            },
            "mapping_reason": f"Автоопределение по ключевым словам в категории '{product.get('category')}'"
        }
    }

@router.post("/migrate")
async def migrate_product(request: MigrateRequest):
    product = repo.get_by_id(request.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    target = request.target_marketplace.lower()
    if target not in Platform.all_values():
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа")
    
    # Проверка на перенос на ту же платформу
    source_platform = product.get("source", "").lower()
    if target in source_platform and "→" not in source_platform:
        raise HTTPException(status_code=400, detail=f"Нельзя перенести товар с {target} на {target}")

    # ЗАПУСК ФОНОВОЙ ЗАДАЧИ CELERY
    task = migrate_product_task.delay(request.product_id, target)
    
    return {
        "success": True,
        "message": "Миграция запущена в фоновом режиме",
        "task_id": task.id,
        "product": repo.get_by_id(request.product_id) # Вернет статус "processing"
    }