"""Фоновое скачивание копий фото товара (Celery)."""

import logging

from celery_app import celery_app
from database.repository import op_log, repo

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.download_photos_task")
def download_photos_task(self, product_id: int, user_id: int):
    """Фоновое скачивание копий фото товара"""
    from services.media_service import download_photos

    product = repo.get_by_id(product_id, user_id=user_id)
    if not product:
        return {"status": "error", "message": "Товар не найден"}

    urls = product.get("photos") or []
    if not urls:
        return {"status": "error", "message": "У товара нет фото"}

    saved = download_photos(product_id, urls)

    try:
        op_log.log_file_operation(
            user_id=user_id,
            operation="media_download",
            platform=None,
            filename=f"товар #{product_id}",
            status="success" if saved else "error",
            total_rows=len(urls),
            imported=len(saved),
            failed=len(urls) - len(saved),
        )
    except Exception as e:
        logger.warning(f"Не удалось записать лог скачивания фото: {e}")

    logger.info(f"💾 Товар {product_id}: скачано {len(saved)} из {len(urls)} фото")
    return {"status": "completed", "saved": len(saved), "total": len(urls)}
