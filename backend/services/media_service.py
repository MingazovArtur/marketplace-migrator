"""
Медиа-сервис: скачивание фото товаров в локальное хранилище,
генерация WebP-миниатюр для галереи (/media/thumbs/...).

Копии хранятся в /app/media/products/{product_id}/ и доступны по /media/...

Безопасность (было 🔴 K-2 из код-ревью):
  каждый URL перед загрузкой проходит SSRF-валидацию (core.ssrf),
  включая каждый переход редиректа — скачивание с внутренних адресов
  (169.254.169.254, localhost, db, redis, приватные сети) заблокировано.
"""

import hashlib
import logging
import os
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image, ImageOps

from core.ssrf import assert_safe_url, safe_get

logger = logging.getLogger(__name__)

DEFAULT_MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", str(DEFAULT_MEDIA_DIR)))
MAX_SIZE_MB = 10
TIMEOUT = 15
ALLOWED_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# Заголовки для обхода защиты CDN маркетплейсов (Ozon / WB / Магнит Маркет)
DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "https://www.ozon.ru/",
}


def _safe_name(url: str) -> str:
    """Детерминированное имя файла: hash URL + расширение (без символов '_' и '/')."""
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext not in ALLOWED_EXT:
        ext = ".jpg"
    digest = hashlib.md5(url.encode()).hexdigest()[:16]
    return f"img-{digest}{ext}"


def download_single_photo(
    product_id: int, url: str, session: httpx.Client | None = None
) -> str | None:
    """
    Скачивает одно фото в MEDIA_ROOT/products/{product_id}/.
    Возвращает относительный путь 'products/{product_id}/{filename}' или None при ошибке.

    Перед запросом URL проверяется на SSRF; редиректы валидируются
    на каждом переходе (safe_get, allow_redirects=False).
    """
    url = (url or "").strip()
    if not url:
        return None

    dest = MEDIA_ROOT / "products" / str(product_id)
    dest.mkdir(parents=True, exist_ok=True)

    path = dest / _safe_name(url)
    # Если файл уже скачан ранее и не пустой — сразу возвращаем путь
    if path.exists() and path.stat().st_size >= 256:
        return f"products/{product_id}/{path.name}"

    own_session = session is None
    sess = session or httpx.Client()
    if own_session:
        sess.headers.update(DOWNLOAD_HEADERS)

    resp = None
    try:
        # SSRF-защита: только публичные http/https, редиректы валидируются
        assert_safe_url(url)
        resp = safe_get(url, session=sess, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()

        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" in content_type:
            raise ValueError(f"Вместо изображения получен HTML ({content_type})")

        size = 0
        with open(path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_SIZE_MB * 1024 * 1024:
                    f.close()
                    path.unlink(missing_ok=True)
                    raise ValueError(f"Файл больше {MAX_SIZE_MB} МБ")
                f.write(chunk)

        if size < 256:
            path.unlink(missing_ok=True)
            raise ValueError("Скачанный файл повреждён или пуст")

        logger.info(f"📥 Фото скачано: {url} ({size} байт)")
        return f"products/{product_id}/{path.name}"
    except ValueError as e:
        # Внутри ValueError — и SSRF-блок, и «не изображение»/«файл повреждён»
        logger.warning(f"⚠️ Скачивание фото отклонено {url}: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Не удалось скачать фото {url}: {e}")
        return None
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass
        if own_session:
            sess.close()


def download_photos(product_id: int, urls: list[str]) -> list[str]:
    """
    Скачивает список фото в MEDIA_ROOT/products/{product_id}/.
    Возвращает список сохранённых относительных путей.

    Собственные /media/products/ URL пропускаем: фото уже локальные,
    а SSRF-защита корректно блокирует их скачивание «из самого себя»
    (в dev они выглядят как http://localhost:8000/media/...).
    """
    saved = []
    with httpx.Client() as session:
        session.headers.update(DOWNLOAD_HEADERS)
        for url in urls:
            if "/media/products/" in str(url):
                continue
            rel_path = download_single_photo(product_id, url, session=session)
            if rel_path:
                saved.append(rel_path)
    return saved


# ---------------------------------------------------------------------------
# Миниатюры (/media/thumbs/...)
# ---------------------------------------------------------------------------

# Предел по длинной стороне (px) — хватит для карточек галереи
THUMB_MAX_SIDE = 320
# Качество WebP (0-100): визуально неотличимо от оригинала в галерее
THUMB_QUALITY = 80
# Дерево миниатюр внутри MEDIA_ROOT: thumbs/<путь оригинала>.webp
THUMB_DIR = "thumbs"


def thumb_path(rel_path: str) -> Path:
    """Путь миниатюры для оригинала rel_path ('products/7/img-<md5>.jpg')."""
    return MEDIA_ROOT / THUMB_DIR / f"{rel_path}.webp"


def get_or_create_thumb(rel_path: str, original: Path) -> Path | None:
    """
    WebP-миниатюра (<= THUMB_MAX_SIDE по длинной стороне), создаётся при
    первом запросе и кэшируется на диске. Имя оригинала детерминировано
    (img-<md5>), поэтому содержимое миниатюры неизменимо — кэшируется навсегда.

    rel_path — путь внутри MEDIA_ROOT (его раздаёт /media, им же проверяется
    ownership); original — уже провалидированный полный путь к файлу.

    Возвращает путь к миниатюре или None (не изображение / битый файл /
    декомпрессионная бомба — Pillow сам ограничивает MAX_IMAGE_PIXELS).

    Атомарность: пишем во временный файл и os.replace — параллельные запросы
    не портят друг друга (последняя запись выигрывает, файл всегда целый).
    """
    rel_path = (rel_path or "").strip().strip("/")
    parts = rel_path.split("/")
    if (
        not rel_path
        or ".." in parts
        or rel_path.startswith(f"{THUMB_DIR}/")
        or os.path.splitext(rel_path)[1].lower() not in ALLOWED_EXT
        or not original.is_file()
    ):
        return None

    thumb = thumb_path(rel_path)
    if thumb.exists() and thumb.stat().st_size > 0:
        return thumb

    thumb.parent.mkdir(parents=True, exist_ok=True)
    tmp = thumb.with_name(f"{thumb.name}.{uuid4().hex}.tmp")
    try:
        with Image.open(original) as img:
            # EXIF-ориентация (снятые вертикально iPhone) + вписывание в квадрат
            img = ImageOps.exif_transpose(img)
            img.thumbnail((THUMB_MAX_SIDE, THUMB_MAX_SIDE))
            # P/CMYK и прочие режимы WebP не умеет — приводим к поддерживаемым
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGBA")
            img.save(tmp, format="WEBP", quality=THUMB_QUALITY)
        os.replace(tmp, thumb)
        logger.info(f"🖼 Миниатюра создана: {rel_path} -> {thumb.name}")
        return thumb
    except Exception as e:
        logger.warning(f"⚠️ Не удалось создать миниатюру {rel_path}: {e}")
        tmp.unlink(missing_ok=True)
        return None
