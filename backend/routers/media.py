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
"""

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

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Media"])

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# фото товаров живут в products/{product_id}/img-<md5>.<ext>
_PRODUCT_PATH = re.compile(r"^products/(\d+)/[^/]+$")


@router.get("/media/{file_path:path}")
async def get_media(
    file_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> FileResponse:
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

    return FileResponse(full_path)
