"""Прокси внешних фото (Hotlink protection CDN) с SSRF-защитой.

Вынесено без изменений из монолита routers/photos.py (Р21).
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from core.rate_limit import limiter
from core.ssrf import safe_get
from services.media_service import DOWNLOAD_HEADERS

logger = logging.getLogger(__name__)
router = APIRouter()

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
        raise HTTPException(status_code=400, detail="Адрес изображения не разрешён") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Не удалось проксировать фото {url}: {e}")
        raise HTTPException(
            status_code=502, detail="Не удалось загрузить внешнее изображение"
        ) from e
