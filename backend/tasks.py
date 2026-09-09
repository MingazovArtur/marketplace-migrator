import logging
from celery_app import celery_app
from database.repository import repo
from services.photo_downloader import PhotoDownloader
from connectors.wildberries import WildberriesConnector
from services.category_mapper import CategoryMapper

logger = logging.getLogger(__name__)
photo_downloader = PhotoDownloader()
category_mapper = CategoryMapper()

@celery_app.task(bind=True, name="tasks.migrate_product_task")
def migrate_product_task(self, product_id: int, target_platform: str):
    """Фоновая задача миграции товара"""
    try:
        # 1. Обновляем статус на "в процессе"
        repo.update(product_id, {"status": "processing"})
        
        product = repo.get_by_id(product_id)
        if not product:
            return {"status": "error", "message": "Товар не найден"}

        # 2. Маппинг категории
        target_category = category_mapper.auto_map_by_text(
            product.get("category") or "Дом и сад", 
            target_platform
        )

        # 3. Имитация работы API (здесь будет реальный вызов коннектора)
        import asyncio
        asyncio.run(asyncio.sleep(2)) # Имитация задержки сети

        # 4. Успешное завершение
        new_source = f"{product['source']} → {target_platform.capitalize()}"
        repo.update(product_id, {
            "status": "success",
            "source": new_source,
            "mapped_category": target_category.get("name", "Неизвестно")
        })
        
        logger.info(f"✅ [Celery] Товар {product_id} успешно перенесен на {target_platform}")
        return {"status": "success", "product_id": product_id}

    except Exception as e:
        logger.error(f"❌ [Celery] Ошибка миграции товара {product_id}: {e}")
        repo.update(product_id, {"status": "error"})
        return {"status": "error", "message": str(e)}