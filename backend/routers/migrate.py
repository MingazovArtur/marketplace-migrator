import logging
from fastapi import APIRouter, HTTPException
from database.repository import repo
from models.schemas import MigrateRequest
from services.category_mapper import CategoryMapper
from core.platforms import Platform, PLATFORM_CONFIG
from tasks import migrate_product_task # <-- Импортируем задачу Celery
from pydantic import BaseModel
from typing import List
from tasks import migrate_batch_task, get_progress

class BatchMigrateRequest(BaseModel):
    product_ids: List[int]
    target_marketplace: str

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
    """Миграция товара с возможностью редактирования данных"""
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

    # === ИСПОЛЬЗУЕМ РЕДАКТИРОВАННЫЕ ДАННЫЕ ИЗ ЗАПРОСА ===
    # Если в запросе есть edited_data, используем их, иначе берем из продукта
    edited_data = request.dict() if hasattr(request, 'edited_data') else {}
    
    final_name = edited_data.get('name') or product.get('name')
    final_price = edited_data.get('price') or product.get('price')
    final_category = edited_data.get('category') or product.get('category')
    
    # Запускаем фоновую задачу с редактированными данными
    task = migrate_product_task.delay(
        request.product_id, 
        target,
        {
            "name": final_name,
            "price": final_price,
            "category": final_category
        }
    )
    
    return {
        "success": True,
        "message": "Миграция запущена в фоновом режиме",
        "task_id": task.id,
        "product": repo.get_by_id(request.product_id)
    }

@router.post("/migrate/batch")
async def migrate_batch(request: BatchMigrateRequest):
    """
    Запуск пакетной миграции нескольких товаров
    Возвращает task_id для отслеживания прогресса
    """
    if not request.product_ids:
        raise HTTPException(status_code=400, detail="Список товаров пуст")
    
    if len(request.product_ids) > 100:
        raise HTTPException(status_code=400, detail="Максимум 100 товаров за раз")
    
    target = request.target_marketplace.lower()
    if target not in Platform.all_values():
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа")

    # Запускаем фоновую задачу
    task = migrate_batch_task.delay(request.product_ids, target)

    return {
        "success": True,
        "task_id": task.id,
        "message": f"Запущена пакетная миграция {len(request.product_ids)} товаров на {target}",
        "total": len(request.product_ids)
    }


@router.get("/tasks/{task_id}/progress")
def get_task_progress(task_id: str):
    """Получить текущий прогресс задачи миграции"""
    progress = get_progress(task_id)
    return {"success": True, "progress": progress}