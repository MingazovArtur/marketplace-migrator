"""Скачивание копий внешних фото на сервер (независимость от чужих CDN).

Вынесено без изменений из монолита routers/photos.py (Р21).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from core.auth import get_current_user
from database.models import User
from database.repository import repo
from routers.photos._support import _build_public_media_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{product_id}/photos/download")
def start_download_photos(
    request: Request,
    product_id: int,
    current_user: User = Depends(get_current_user),
):
    """
    Скачать копии внешних фото на сервер и обновить ссылки товара на локальные копии,
    чтобы они гарантированно отображались в браузере и не зависели от блокировок чужих CDN.
    """
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    photos = product.get("photos") or []
    if not photos:
        raise HTTPException(status_code=400, detail="У товара нет фото для скачивания")

    from services.media_service import download_single_photo

    new_photos = []
    downloaded_count = 0
    for url in photos:
        # Если фото уже лежит в нашем /media/, оставляем как есть
        if "/media/products/" in str(url):
            new_photos.append(url)
            continue
        rel_path = download_single_photo(product_id, url)
        if rel_path:
            new_photos.append(_build_public_media_url(request, rel_path))
            downloaded_count += 1
        else:
            new_photos.append(url)

    repo.update(
        product_id,
        {"photos": new_photos, "photos_count": len(new_photos)},
        user_id=current_user.id,
    )

    return {
        "success": True,
        "downloaded": downloaded_count,
        "photos": new_photos,
        "count": len(new_photos),
    }
