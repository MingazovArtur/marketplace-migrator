"""Общие константы и утилиты роутера фотографий.

Вынесено без изменений из монолита routers/photos.py (Р21): лимиты
загрузки (размер/количество/расширения), Pydantic-модель PhotosUpdate
и построение полного публичного URL медиафайла.
"""

import logging

from fastapi import Request
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 МБ (требование Ozon)
MAX_PHOTOS_PER_PRODUCT = 30


class PhotosUpdate(BaseModel):
    photos: list[str]


def _build_public_media_url(request: Request, rel_path: str) -> str:
    """
    Формирует полный URL до медиафайла.
    Это важно:
      1) чтобы в локальной разработке (фронт :5173, бэк :8000) картинки открывались с :8000;
      2) чтобы при экспорте в XLSX Ozon получал полный http(s):// адрес, а не относительный /media/...
    """
    public = (settings.PUBLIC_URL or "").strip().rstrip("/")
    # Если PUBLIC_URL указывает на dev-фронт (:5173/:3000), берём базовый URL самого бэкенда
    if not public or ":5173" in public or ":3000" in public:
        base = str(request.base_url).rstrip("/")
    else:
        base = public
    return f"{base}/media/{rel_path.lstrip('/')}"
