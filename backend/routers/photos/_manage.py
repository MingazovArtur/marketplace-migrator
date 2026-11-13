"""Чтение и замена списка фото товара (порядок важен: первое — главное).

Вынесено без изменений из монолита routers/photos.py (Р21).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from core.auth import get_current_user
from database.models import User
from database.repository import repo
from routers.photos._support import MAX_PHOTOS_PER_PRODUCT, PhotosUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


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

    seen = set()
    photos = []
    for url in payload.photos:
        u = str(url or "").strip()
        if u and u not in seen:
            seen.add(u)
            photos.append(u)

    if len(photos) > MAX_PHOTOS_PER_PRODUCT:
        raise HTTPException(status_code=400, detail=f"Максимум {MAX_PHOTOS_PER_PRODUCT} фото на товар")

    repo.update(
        product_id,
        {"photos": photos, "photos_count": len(photos)},
        user_id=current_user.id,
    )
    logger.info(f"🖼 Товар {product_id}: обновлено фото, всего {len(photos)}")
    return {"success": True, "photos": photos, "count": len(photos)}
