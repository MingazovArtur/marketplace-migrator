"""
Роутер управления фотографиями товара: порядок, добавление, удаление, скачивание копий.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import get_current_user
from database.models import User
from database.repository import repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/products", tags=["Photos"])


class PhotosUpdate(BaseModel):
    photos: list[str]


@router.get("/{product_id}/photos")
def get_photos(product_id: int, current_user: User = Depends(get_current_user)):
    """Получить список фото товара"""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    photos = product.get("photos") or []
    return {"success": True, "photos": photos, "count": len(photos)}


@router.put("/{product_id}/photos")
def set_photos(
    product_id: int,
    payload: PhotosUpdate,
    current_user: User = Depends(get_current_user),
):
    """Заменить список фото (порядок важен: первое — главное)"""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    # Чистим: пустые строки и дубликаты убираем, порядок сохраняем
    seen = set()
    photos = []
    for url in payload.photos:
        u = str(url or "").strip()
        if u and u not in seen:
            seen.add(u)
            photos.append(u)

    if len(photos) > 30:
        raise HTTPException(status_code=400, detail="Максимум 30 фото на товар")

    repo.update(
        product_id,
        {"photos": photos, "photos_count": len(photos)},
        user_id=current_user.id,
    )
    logger.info(f"🖼 Товар {product_id}: обновлено фото, всего {len(photos)}")
    return {"success": True, "photos": photos, "count": len(photos)}


@router.post("/{product_id}/photos/download")
def start_download_photos(
    product_id: int,
    current_user: User = Depends(get_current_user),
):
    """Запустить фоновое скачивание копий фото на сервер"""
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    photos = product.get("photos") or []
    if not photos:
        raise HTTPException(status_code=400, detail="У товара нет фото для скачивания")

    from tasks import download_photos_task

    task = download_photos_task.delay(product_id, current_user.id)
    return {"success": True, "task_id": task.id, "photos": len(photos)}
