import logging
import time
from celery_app import celery_app
from database.repository import repo
from services.category_mapper import CategoryMapper
from services.category_service import category_service
from core.platforms import Platform, PLATFORM_CONFIG

logger = logging.getLogger(__name__)
category_mapper = CategoryMapper()

# Утилита для определения платформы (дублируем логику из App.jsx для бэкенда)
def detect_platform(source_str: str) -> str:
    if not source_str: return None
    s = source_str.lower()
    if '→' in s:
        last = s.split('→')[-1].strip()
        if 'ozon' in last: return 'ozon'
        if 'wildberries' in last or 'wb' in last: return 'wildberries'
        if 'яндекс' in last or 'yandex' in last: return 'yandex'
    if 'ozon' in s: return 'ozon'
    if 'wildberries' in s or 'wb' in s: return 'wildberries'
    if 'яндекс' in s or 'yandex' in s: return 'yandex'
    return None


def update_progress(task_id, current, total, status="processing", success=0, errors=0, error_details=None):
    """Обновляет прогресс задачи в Redis"""
    try:
        celery_app.backend.store_result(
            task_id,
            {
                "current": current, "total": total,
                "percent": round((current / total) * 100, 1) if total > 0 else 0,
                "status": status, "success": success, "errors": errors,
                "error_details": error_details or []
            },
            state="PROGRESS"
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить прогресс: {e}")


def get_progress(task_id: str):
    """Получает текущий прогресс задачи по её ID (нужна для migrate.py)"""
    try:
        result = celery_app.AsyncResult(task_id)
        if result.state == "PROGRESS":
            return result.info
        elif result.state == "SUCCESS":
            # Гарантируем, что фронтенд всегда получит статус "completed" для успешных задач
            task_result = result.result
            if isinstance(task_result, dict) and task_result.get("status") == "success":
                task_result["status"] = "completed"
            return task_result
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
def migrate_product_task(self, product_id: int, target_platform: str, user_id: int, edited_data: dict = None):
    """Фоновая задача для одиночной миграции товара"""
    try:
        repo.update(product_id, {"status": "processing"})
        product = repo.get_by_id(product_id)
        if not product:
            return {"status": "error", "message": "Товар не найден"}

        source_platform = detect_platform(product.get("source"))
        category_name = edited_data.get("category") if edited_data else product.get("category")

        # === ГЛАВНОЕ ИЗМЕНЕНИЕ: Проверяем ручной маппинг ===
        mapping = category_service.get_mapping_for_product(
            source_platform, category_name, target_platform, user_id
        )

        if mapping and mapping.get("is_manual"):
            target_category_name = mapping["target_category_name"]
            logger.info(f"✅ Использован ручной маппинг: {category_name} -> {target_category_name}")
        else:
            # Fallback на авто-маппинг
            auto_map = category_mapper.auto_map_by_text(category_name or "Дом и сад", target_platform)
            target_category_name = auto_map.get("name", "Неизвестно")
            logger.info(f"ℹ️ Использован авто-маппинг: {category_name} -> {target_category_name}")

        time.sleep(1) # Имитация задержки сети

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
        })
        
        # 🔧 ИСПРАВЛЕНИЕ: возвращаем "completed" вместо "success", чтобы фронтенд понял, что задача завершена
        return {"status": "completed", "product_id": product_id}

    except Exception as e:
        logger.error(f"❌ Ошибка миграции товара {product_id}: {e}")
        repo.update(product_id, {"status": "error"})
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
            product = repo.get_by_id(product_id)
            if not product:
                error_count += 1
                errors.append({"id": product_id, "error": "Товар не найден"})
                update_progress(self.request.id, index, total, "processing", success_count, error_count, errors)
                continue

            source_platform = detect_platform(product.get("source"))
            category_name = product.get("category")

            # === Проверяем ручной маппинг ===
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
            })
            success_count += 1
            
        except Exception as e:
            error_count += 1
            errors.append({"id": product_id, "error": str(e)})
            repo.update(product_id, {"status": "error"})

        update_progress(self.request.id, index, total, "processing", success_count, error_count, errors)

    result = {
        "status": "completed", "total": total, "success": success_count,
        "errors": error_count, "error_details": errors[:10], "percent": 100
    }
    celery_app.backend.store_result(self.request.id, result, state="SUCCESS")
    logger.info(f"🎯 Пакетная миграция завершена: {success_count}/{total} успешно")
    return result