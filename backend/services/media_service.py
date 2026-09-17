"""
Медиа-сервис: скачивание фото товаров в локальное хранилище.
Копии хранятся в /app/media/products/{product_id}/ и доступны по /media/...
"""
import os
import hashlib
import logging
from pathlib import Path
from typing import List

import requests

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/app/media"))
MAX_SIZE_MB = 10
TIMEOUT = 15
ALLOWED_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _safe_name(url: str) -> str:
    """Детерминированное имя файла: hash URL + расширение."""
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext not in ALLOWED_EXT:
        ext = ".jpg"
    digest = hashlib.md5(url.encode()).hexdigest()[:16]
    return f"{digest}{ext}"


def download_photos(product_id: int, urls: List[str]) -> List[str]:
    """
    Скачивает фото в MEDIA_ROOT/products/{product_id}/.
    Возвращает список сохранённых относительных путей.
    Ошибки по отдельным фото не роняют задачу — только warning в лог.
    """
    dest = MEDIA_ROOT / "products" / str(product_id)
    dest.mkdir(parents=True, exist_ok=True)

    saved = []
    for url in urls:
        try:
            resp = requests.get(url, timeout=TIMEOUT, stream=True)
            resp.raise_for_status()

            path = dest / _safe_name(url)
            size = 0
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    size += len(chunk)
                    if size > MAX_SIZE_MB * 1024 * 1024:
                        path.unlink(missing_ok=True)
                        raise ValueError(f"Файл больше {MAX_SIZE_MB} МБ")
                    f.write(chunk)

            saved.append(f"products/{product_id}/{path.name}")
            logger.info(f"📥 Фото скачано: {url}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось скачать фото {url}: {e}")

    return saved