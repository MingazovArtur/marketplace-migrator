"""
Раздача медиа-файлов (фото товаров) с авторизацией.

Было: /media раздавался без авторизации (nginx alias /var/media + StaticFiles) —
фото товара видел любой, у кого есть URL. Стало: запрос проходит через
get_current_user, файл отдаётся только владельцу товара (или админу).

Правила:
  - токен: httpOnly-cookie (ставится при логине) или Authorization: Bearer;
  - путь строго внутри MEDIA_DIR (path traversal отсекается);
  - products/{id}/... — только владелец товара или админ;
  - несуществующее/чужое — 404 (не раскрываем существование).

Миниатюры (Round 8):
  - GET /media/thumbs/products/{id}/img.jpg — WebP <= 320px, генерируется
    из оригинала при первом запросе (Pillow) и кэшируется на диске;
    ownership проверяется по пути ОРИГИНАЛА (products/{id}/...);
  - /media/thumbs/... объявлен ДО catch-all /media/{path} (порядок матчинга),
    а сам catch-all путь thumbs/... отклоняет — миниатюры не отдать в обход
    ownership-контроля оригинала.
"""

import asyncio
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from database.models import Product, User
from database.session import get_async_db
from services.media_service import get_or_create_thumb

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Media"])

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# фото товаров живут в products/{product_id}/img-<md5>.<ext>
_PRODUCT_PATH = re.compile(r"^products/(\d+)/[^/]+$")

# Миниатюра неизменима (имя оригинала детерминировано: img-<md5>) — кэш навсегда
_THUMB_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}


async def _check_media_access(file_path: str, current_user: User, db: AsyncSession) -> Path:
    """
    Валидация пути + ownership для ОРИГИНАЛА file_path (products/{id}/...).

    Возвращает полный путь к файлу или бросает 404 (не раскрываем существование).
    Общий код /media и /media/thumbs — правила доступа идентичны.
    """
    # 1) нормализация и защита от path traversal (../, абсолютные пути, symlink)
    try:
        full_path = (MEDIA_DIR / file_path).resolve()
        full_path.relative_to(MEDIA_DIR.resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Файл не найден") from None

    if full_path.suffix.lower() not in ALLOWED_EXT or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")

    # 2) ownership: products/{product_id}/... — владелец или админ
    m = _PRODUCT_PATH.match(file_path)
    if m:
        product_id = int(m.group(1))
        if current_user.role != "admin":
            res = await db.execute(
                select(Product.id).where(
                    Product.id == product_id, Product.user_id == current_user.id
                )
            )
            if res.scalars().first() is None:
                raise HTTPException(status_code=404, detail="Файл не найден")

    return full_path


@router.get("/media/thumbs/{file_path:path}")
async def get_media_thumb(
    file_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> FileResponse:
    """WebP-миниатюра фото (<= 320px), генерируется при первом запросе.

    file_path — путь ОРИГИНАЛА (products/{id}/img-<md5>.jpg): права те же,
    что у /media/... — владелец товара или админ. Генерация (Pillow, дисковый
    ввод-вывод) уходит в threadpool, event loop не блокируется.
    """
    full_path = await _check_media_access(file_path, current_user, db)

    thumb = await asyncio.to_thread(get_or_create_thumb, file_path, full_path)
    if thumb is None:
        # битый файл / не изображение / декомпрессионная бомба
        raise HTTPException(status_code=404, detail="Файл не найден")

    return FileResponse(thumb, media_type="image/webp", headers=_THUMB_CACHE_HEADERS)


@router.get("/media/{file_path:path}")
async def get_media(
    file_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> FileResponse:
    # Миниатюры — только через /media/thumbs/... (ownership проверяется по
    # пути оригинала; напрямую из дерева thumbs/ не отдаём даже админу)
    if file_path.startswith("thumbs/"):
        raise HTTPException(status_code=404, detail="Файл не найден")

    full_path = await _check_media_access(file_path, current_user, db)
    return FileResponse(full_path)
