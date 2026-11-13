"""Загрузка фото с компьютера в карточку товара (multipart).

Вынесено без изменений из монолита routers/photos.py (Р21).
"""

import hashlib
import logging
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from core.auth import get_current_user
from database.models import User
from database.repository import repo
from routers.photos._support import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_PHOTOS_PER_PRODUCT,
    _build_public_media_url,
)
from services.media_service import MEDIA_ROOT

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{product_id}/photos/upload")
async def upload_photo_files(
    request: Request,
    product_id: int,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Загрузить одно или несколько фото с компьютера в карточку товара.
    Файлы сохраняются в /app/media/products/{product_id}/ и сразу привязываются к товару.
    """
    product = repo.get_by_id(product_id, user_id=current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    existing_photos = list(product.get("photos") or [])
    if len(existing_photos) + len(files) > MAX_PHOTOS_PER_PRODUCT:
        raise HTTPException(
            status_code=400,
            detail=f"Превышен лимит фотографий ({MAX_PHOTOS_PER_PRODUCT} шт. на товар)",
        )

    dest_dir = Path(MEDIA_ROOT) / "products" / str(product_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    uploaded_urls = []
    for upload in files:
        if not upload.filename:
            continue
        ext = os.path.splitext(upload.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Файл «{upload.filename}»: поддерживаются только JPG, JPEG, PNG, WEBP",
            )

        data = await upload.read()
        if not data:
            continue
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Файл «{upload.filename}» превышает лимит 10 МБ",
            )

        # Формируем безопасное имя файла без символов '/' и '_' (требование Ozon к именам фото)
        digest = hashlib.md5(data).hexdigest()[:12]
        rand_suffix = secrets.token_hex(3)
        safe_filename = f"photo-{digest}-{rand_suffix}{ext}"
        file_path = dest_dir / safe_filename
        file_path.write_bytes(data)

        rel_path = f"products/{product_id}/{safe_filename}"
        public_url = _build_public_media_url(request, rel_path)
        uploaded_urls.append(public_url)
        if public_url not in existing_photos:
            existing_photos.append(public_url)

    repo.update(
        product_id,
        {"photos": existing_photos, "photos_count": len(existing_photos)},
        user_id=current_user.id,
    )

    logger.info(
        f"📤 Товар {product_id}: загружено {len(uploaded_urls)} файлов фото, всего {len(existing_photos)}"
    )
    return {
        "success": True,
        "uploaded": uploaded_urls,
        "photos": existing_photos,
        "count": len(existing_photos),
    }
