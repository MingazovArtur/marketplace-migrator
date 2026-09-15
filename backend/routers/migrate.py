"""
Роутер для миграции товаров между маркетплейсами
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from database.repository import repo
from models.schemas import MigrateRequest, BatchMigrateRequest
from services.category_mapper import CategoryMapper
from services.category_service import category_service
from core.platforms import Platform, PLATFORM_CONFIG
from core.auth import get_current_user
from database.models import User
from tasks import migrate_product_task, migrate_batch_task, get_progress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Migration"])
category_mapper = CategoryMapper()


@router.post("/migrate/preview")
async def preview_migration(
    request: MigrateRequest,
    current_user: User = Depends(get_current_user)
):
    """Предпросмотр миграции товара"""
    product = repo.get_by_id(request.product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")
    
    target = request.target_marketplace.lower()
    source_platform = product.get("source", "").lower().split('→')[-1].strip()
    if 'ozon' in source_platform: source_platform = 'ozon'
    elif 'wildberries' in source_platform or 'wb' in source_platform: source_platform = 'wildberries'
    elif 'яндекс' in source_platform or 'yandex' in source_platform: source_platform = 'yandex'

    mapping = category_service.get_mapping_for_product(
        source_platform, product.get("category"), target, current_user.id
    )

    if mapping and mapping.get("is_manual"):
        target_category_name = mapping["target_category_name"]
        reason = "Использован ваш ручной маппинг"
    else:
        auto_map = category_mapper.auto_map_by_text(product.get("category") or "Дом и сад", target)
        target_category_name = auto_map["name"]
        reason = f"Автоопределение по ключевым словам в категории '{product.get('category')}'"
    
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
                "category": target_category_name,
                "category_id": mapping["target_category_id"] if mapping else None
            },
            "mapping_reason": reason
        }
    }


@router.post("/migrate")
async def migrate_product(
    request: MigrateRequest,
    current_user: User = Depends(get_current_user)
):
    """Запустить миграцию одного товара"""
    product = repo.get_by_id(request.product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")
    
    # ✅ Убрано дублирование — одна проверка вместо двух
    if product.get("status") == "processing":
        raise HTTPException(
            status_code=400,
            detail="Товар уже находится в процессе переноса. Дождитесь завершения."
        )
    
    target = request.target_marketplace.lower()
    if target not in Platform.all_values():
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа")
    
    source_platform = product.get("source", "").lower()
    if target in source_platform and "→" not in source_platform:
        raise HTTPException(status_code=400, detail=f"Нельзя перенести товар с {target} на {target}")

    task = migrate_product_task.delay(
        request.product_id,
        target,
        current_user.id,
        request.dict().get("edited_data")
    )
    
    return {
        "success": True,
        "message": "Миграция запущена в фоновом режиме",
        "task_id": task.id,
        "product": repo.get_by_id(request.product_id, user_id=current_user.id)
    }


@router.post("/migrate/batch")
async def migrate_batch(
    request: BatchMigrateRequest,
    current_user: User = Depends(get_current_user)
):
    """Запустить пакетную миграцию товаров"""
    if not request.product_ids:
        raise HTTPException(status_code=400, detail="Список товаров пуст")
    if len(request.product_ids) > 100:
        raise HTTPException(status_code=400, detail="Максимум 100 товаров за раз")
    
    available_ids = []
    for pid in request.product_ids:
        product = repo.get_by_id(pid, user_id=current_user.id)
        if product and product.get("status") != "processing":
            available_ids.append(pid)
    
    if not available_ids:
        raise HTTPException(
            status_code=400,
            detail="Все выбранные товары уже находятся в процессе переноса или не принадлежат вам"
        )
    
    target = request.target_marketplace.lower()
    if target not in Platform.all_values():
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа")

    task = migrate_batch_task.delay(available_ids, target, current_user.id)

    return {
        "success": True,
        "task_id": task.id,
        "message": f"Запущена пакетная миграция {len(available_ids)} товаров на {target}",
        "total": len(available_ids)
    }


@router.get("/tasks/{task_id}/progress")
def get_task_progress(task_id: str):
    """Получить прогресс задачи миграции"""
    progress = get_progress(task_id)
    return {"success": True, "progress": progress}