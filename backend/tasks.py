import logging
import time
from celery_app import celery_app
from database.repository import repo
from services.category_mapper import CategoryMapper
from core.platforms import Platform, PLATFORM_CONFIG

logger = logging.getLogger(__name__)
category_mapper = CategoryMapper()


def update_progress(task_id, current, total, status="processing", success=0, errors=0, error_details=None):
    """Обновляет прогресс задачи в Redis"""
    try:
        celery_app.backend.store_result(
            task_id,
            {
                "current": current,
                "total": total,
                "percent": round((current / total) * 100, 1) if total > 0 else 0,
                "status": status,
                "success": success,
                "errors": errors,
                "error_details": error_details or []
            },
            state="PROGRESS"
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить прогресс: {e}")


def get_progress(task_id: str):
    """Получает текущий прогресс задачи по её ID"""
    try:
        result = celery_app.AsyncResult(task_id)
        if result.state == "PROGRESS":
            return result.info
        elif result.state == "SUCCESS":
            return result.result
        elif result.state == "FAILURE":
            return {"status": "error", "message": str(result.result)}
        return {
            "status": "pending", 
            "current": 0, 
            "total": 0, 
            "percent": 0, 
            "success": 0, 
            "errors": 0,
            "error_details": []
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="tasks.migrate_product_task")
def migrate_product_task(self, product_id: int, target_platform: str, edited_data: dict = None):
    """Фоновая задача для миграции товара с возможностью редактирования"""
    try:
        repo.update(product_id, {"status": "processing"})
        product = repo.get_by_id(product_id)
        if not product:
            return {"status": "error", "message": "Товар не найден"}

        # Используем редактированные данные или берем из продукта
        final_name = edited_data.get("name") if edited_data else product.get("name")
        final_price = edited_data.get("price") if edited_data else product.get("price")
        final_category = edited_data.get("category") if edited_data else product.get("category")

        target_category = category_mapper.auto_map_by_text(
            final_category or "Дом и сад", 
            target_platform
        )
        
        time.sleep(1) # Имитация задержки сети

        new_source = f"{product['source']} → {PLATFORM_CONFIG[target_platform]['name']}"
        repo.update(product_id, {
            "status": "success",
            "source": new_source,
            "name": final_name,  # Обновляем название
            "price": final_price,  # Обновляем цену
            "category": final_category,  # Обновляем категорию
            "mapped_category": target_category.get("name", "Неизвестно")
        })
        
        logger.info(f"✅ Товар {product_id} успешно перенесен на {target_platform}")
        return {"status": "success", "product_id": product_id}

    except Exception as e:
        logger.error(f"❌ Ошибка миграции товара {product_id}: {e}")
        repo.update(product_id, {"status": "error"})
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="tasks.migrate_batch_task")
def migrate_batch_task(self, product_ids: list, target_platform: str):
    """Пакетная миграция товаров с отслеживанием прогресса"""
    total = len(product_ids)
    success_count = 0
    error_count = 0
    errors = []

    for index, product_id in enumerate(product_ids, 1):
        try:
            product = repo.get_by_id(product_id)
            if not product:
                error_count += 1
                errors.append({"id": product_id, "error": "Товар не найден"})
                update_progress(self.request.id, index, total, "processing", success_count, error_count, errors)
                continue

            target_category = category_mapper.auto_map_by_text(
                product.get("category") or "Дом и сад", 
                target_platform
            )
            
            time.sleep(1) # Имитация задержки сети (1 сек на товар)

            new_source = f"{product['source']} → {PLATFORM_CONFIG[target_platform]['name']}"
            repo.update(product_id, {
                "status": "success",
                "source": new_source,
                "mapped_category": target_category.get("name", "Неизвестно")
            })
            success_count += 1
            
        except Exception as e:
            error_count += 1
            errors.append({"id": product_id, "error": str(e)})
            repo.update(product_id, {"status": "error"})

        # Обновляем прогресс после каждого товара
        update_progress(self.request.id, index, total, "processing", success_count, error_count, errors)

    # Финальный результат
    result = {
        "status": "completed",
        "total": total,
        "success": success_count,
        "errors": error_count,
        "error_details": errors[:10],
        "percent": 100
    }

    celery_app.backend.store_result(self.request.id, result, state="SUCCESS")
    logger.info(f"🎯 Пакетная миграция завершена: {success_count}/{total} успешно")
    return result