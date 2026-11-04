"""
Роутер управления фотографиями товара: порядок, добавление по ссылке,
загрузка файлов с компьютера, скачивание копий и проксирование защищённых CDN.
"""

import hashlib
import logging
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from core.auth import get_current_user
from core.config import settings
from core.rate_limit import limiter
from core.ssrf import safe_get
from database.models import User
from database.repository import repo
from services.media_service import DOWNLOAD_HEADERS, MEDIA_ROOT

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/products", tags=["Photos"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 МБ (требование Ozon)
MAX_PHOTOS_PER_PRODUCT = 30

# Только изображения: прокси не должен служить «универсальным загрузчиком»
PROXY_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/avif",
    "image/bmp",
}
PROXY_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 МБ — защита от bandwidth-усиления


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


@router.get("/photos/proxy")
@limiter.limit("30/minute")
def proxy_external_photo(
    request: Request,
    url: str = Query(..., description="Внешний URL картинки"),
):
    """
    Прокси для отображения фотографий с внешних CDN (Ozon, WB, Яндекс Маркет),
    которые блокируют прямой показ (Hotlink protection / Referer check) в браузере.

    Аутентификация НЕДОСТУПНА осознанно: фронт подставляет этот URL в <img src>,
    а браузер не отправляет Authorization-заголовки для картинок. Полное закрытие
    (HMAC-подписанные URL / blob-fetch) — кандидат в Неделю 2.

    Компенсирующие контроли (было 🔴 K-1 — открытый SSRF-прокси):
      - SSRF-валидация адреса и КАЖДОГО редиректа (core.ssrf.safe_get):
        внутренние адреса (169.254.169.254, localhost, db, приватные сети) недоступны;
      - только изображения (белый список Content-Type) — не «универсальный загрузчик»;
      - лимит ответа 10 МБ — нет bandwidth-усиления;
      - 30 запросов/мин (IP для анонимов, user_id при наличии JWT) + глобальный ban-check.
    """
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Некорректный URL изображения")

    try:
        # safe_get: валидирует URL и каждый переход редиректа,
        # блокируя обращения к внутренней сети (169.254.169.254, localhost, db, ...)
        resp = safe_get(
            url,
            headers=DOWNLOAD_HEADERS,
            timeout=12,
            stream=True,
        )
        resp.raise_for_status()

        content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type not in PROXY_ALLOWED_CONTENT_TYPES:
            resp.close()
            raise HTTPException(
                status_code=415,
                detail=f"По адресу отдаётся не изображение ({content_type or 'неизвестный тип'})",
            )

        size = 0
        chunks = []
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > PROXY_MAX_SIZE_BYTES:
                resp.close()
                raise HTTPException(
                    status_code=413,
                    detail="Изображение больше 10 МБ — прокси не отдаёт его",
                )
            chunks.append(chunk)

        content = b"".join(chunks)
        resp.close()
        return Response(
            content=content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except ValueError as e:
        # SSRF-защита: запрещённый адрес/редирект
        logger.warning(f"🚫 Прокси фото отклонён (SSRF): {url} — {e}")
        raise HTTPException(status_code=400, detail="Адрес изображения не разрешён")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Не удалось проксировать фото {url}: {e}")
        raise HTTPException(status_code=502, detail="Не удалось загрузить внешнее изображение")


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