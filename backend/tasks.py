"""
Celery задачи для фоновой миграции товаров
"""
import logging
import time
from celery_app import celery_app
from database.repository import repo
from services.category_mapper import CategoryMapper
from services.category_service import category_service
from services.platform_utils import detect_platform  # ✅ Единый импорт
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
            task_result = result.result
            if isinstance(task_result, dict) and task_result.get("status") == "success":
                task_result["status"] = "completed"
            return task_result
        elif result.state == "FAILURE":
            return {"status": "error", "message": str(result.result)}
        return {
            "status": "pending",
            "current": 0, "total": 0, "percent": 0,
            "success": 0, "errors": 0, "error_details": []
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="tasks.migrate_product_task")
def migrate_product_task(self, product_id: int, target_platform: str, user_id: int, edited_data: dict = None):
    """Фоновая задача для одиночной миграции товара"""
    try:
        product = repo.get_by_id(product_id, user_id=user_id)
        if not product:
            logger.error(f"Товар {product_id} не найден или не принадлежит пользователю {user_id}")
            return {"status": "error", "message": "Товар не найден или не принадлежит вам"}

        repo.update(product_id, {"status": "processing"}, user_id=user_id)

        source_platform = detect_platform(product.get("source"))
        category_name = edited_data.get("category") if edited_data else product.get("category")

        mapping = category_service.get_mapping_for_product(
            source_platform, category_name, target_platform, user_id
        )

        if mapping and mapping.get("is_manual"):
            target_category_name = mapping["target_category_name"]
            logger.info(f"Использован ручной маппинг: {category_name} -> {target_category_name}")
        else:
            auto_map = category_mapper.auto_map_by_text(category_name or "Дом и сад", target_platform)
            target_category_name = auto_map.get("name", "Неизвестно")
            logger.info(f"Использован авто-маппинг: {category_name} -> {target_category_name}")

        time.sleep(1)

        final_name = edited_data.get("name") if edited_data else product.get("name")
        final_price = edited_data.get("price") if edited_data else product.get("price")
        new_source = f"{product['source']} → {PLATFORM_CONFIG[target_platform]['name']}"
        
        repo.update(product_id, {
            "status": "success",
            "source": new_source,
            "name": final_name,
            "price": final_price,
            "category": category_name,
            "mapped_category": target_category_name
        }, user_id=user_id)

        logger.info(f"Товар {product_id} успешно мигрирован пользователем {user_id}")
        return {"status": "completed", "product_id": product_id}

    except Exception as e:
        logger.error(f"Ошибка миграции товара {product_id}: {e}")
        repo.update(product_id, {"status": "error"}, user_id=user_id)
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="tasks.migrate_batch_task")
def migrate_batch_task(self, product_ids: list, target_platform: str, user_id: int):
    """Пакетная миграция товаров с отслеживанием прогресса"""
    total = len(product_ids)
    success_count = 0
    error_count = 0
    errors = []

    for index, product_id in enumerate(product_ids, 1):
        try:
            product = repo.get_by_id(product_id, user_id=user_id)
            if not product:
                error_count += 1
                errors.append({"id": product_id, "error": "Товар не найден или не принадлежит вам"})
                update_progress(self.request.id, index, total, "processing", success_count, error_count, errors)
                continue

            source_platform = detect_platform(product.get("source"))
            category_name = product.get("category")

            mapping = category_service.get_mapping_for_product(
                source_platform, category_name, target_platform, user_id
            )

            if mapping and mapping.get("is_manual"):
                target_category_name = mapping["target_category_name"]
            else:
                auto_map = category_mapper.auto_map_by_text(category_name or "Дом и сад", target_platform)
                target_category_name = auto_map.get("name", "Неизвестно")

            time.sleep(1)

            new_source = f"{product['source']} → {PLATFORM_CONFIG[target_platform]['name']}"
            repo.update(product_id, {
                "status": "success",
                "source": new_source,
                "mapped_category": target_category_name
            }, user_id=user_id)
            
            success_count += 1

        except Exception as e:
            error_count += 1
            errors.append({"id": product_id, "error": str(e)})
            repo.update(product_id, {"status": "error"}, user_id=user_id)

        update_progress(self.request.id, index, total, "processing", success_count, error_count, errors)

    result = {
        "status": "completed",
        "total": total,
        "success": success_count,
        "errors": error_count,
        "error_details": errors[:10],
        "percent": 100
    }
    celery_app.backend.store_result(self.request.id, result, state="SUCCESS")
    logger.info(f"Пакетная миграция завершена пользователем {user_id}: {success_count}/{total} успешно")
    return result