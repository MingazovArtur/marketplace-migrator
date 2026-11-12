"""
Обновление спецификаций категорий площадки через её API (единый формат).

Все поддерживаемые площадки (Ozon, Яндекс Маркет, Wildberries) запускаются
в фоне через Celery (refresh_specs_task) и отдают прогресс через
/specs/{platform}/refresh/{task_id}/progress.

ВАЖНО: маршруты этого модуля — фиксированные пути под /specs/{platform}/*,
они обязаны регистрироваться ДО catch-all /specs/{platform}/{category_id:path}
(порядок сборки — в routers/categories/__init__.py).

Вынесено без изменений из монолита routers/categories.py (Р7).
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from core.auth import get_current_user
from core.config import settings
from core.crypto import encrypt_str
from database.models import User
from models.schemas import RefreshSpecRequest
from services import cache_service, specs_monitor
from tasks import get_progress, refresh_specs_task

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/specs/{platform}/refresh")
async def refresh_specs(
    platform: str,
    payload: RefreshSpecRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Единый формат обновления спецификаций категорий площадки через её API.
    Для всех поддерживаемых площадок (Ozon, Яндекс Маркет, Wildberries) запускает
    фоновую задачу Celery и возвращает task_id для отслеживания прогресса
    через /specs/{platform}/refresh/{task_id}/progress.
    """
    platform = platform.lower().strip()
    if platform not in ("ozon", "yandex", "wildberries"):
        raise HTTPException(status_code=501, detail=f"Загрузчик для {platform} ещё не реализован")

    raw_key = (payload.api_key or "").strip()
    business_id = (str(payload.business_id).strip() if payload.business_id else "")

    # Если для Ozon переданы раздельно business_id (как Client ID) и api_key (как UUID)
    if platform == "ozon" and raw_key and ":" not in raw_key and business_id:
        raw_key = f"{business_id}:{raw_key}"

    if not raw_key and platform == "ozon" and settings.OZON_CLIENT_ID and settings.OZON_API_KEY:
        raw_key = f"{settings.OZON_CLIENT_ID}:{settings.OZON_API_KEY}"

    if not raw_key:
        raise HTTPException(status_code=400, detail="Не указан API-ключ площадки")

    if platform == "yandex" and not business_id:
        raise HTTPException(
            status_code=400,
            detail="Для Яндекс Маркета укажите номер кабинета (ID кабинета / business_id) и OAuth-токен",
        )

    try:
        cache_service.delete_pattern(f"specs:{platform}:*")

        # В-4 (неделя 2): ключ шифруется перед публикацией в Redis —
        # в брокере не остаётся plaintext API-ключей (decrypt — в воркере).
        # Тот же шифротекст сохраняется в реестре мониторинга, чтобы админ
        # мог продолжить остановленную загрузку без повторного ввода ключа.
        enc_key = encrypt_str(raw_key)

        task = refresh_specs_task.delay(
            user_id=current_user.id,
            platform=platform,
            raw_api_key=enc_key,
            category_ids=payload.category_ids,
            business_id=business_id or None,
        )
        # Реестр мониторинга (админ-страница): задача сразу видна как «в очереди» —
        # до этого параллельные загрузки в solo-воркере были невидимы
        specs_monitor.register(
            task.id,
            platform=platform,
            user_id=current_user.id,
            username=current_user.username,
            resume_params={
                "enc_key": enc_key,
                "category_ids": payload.category_ids,
                "business_id": business_id or None,
                "skip_category_ids": [],
            },
        )
        logger.info(f"Specs refresh queued [{platform}]: task_id={task.id}, user={current_user.id}")
        return {
            "success": True,
            "task_id": task.id,
            "platform": platform,
            "message": f"Загрузка спецификаций {platform} запущена в фоне",
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка API площадки: {e.response.status_code} — {e.response.text[:200]}",
        )


@router.get("/specs/{platform}/refresh/{task_id}/progress")
def refresh_specs_progress(
    platform: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Прогресс фоновой загрузки спеков (единый формат для всех площадок)."""
    return get_progress(task_id)


@router.get("/specs/{platform}/key-source")
def spec_key_source(platform: str, current_user: User = Depends(get_current_user)):
    """
    Индикатор: есть ли серверный ключ площадки в .env.
    При ошибке возвращает has_server_key=False + hint.
    """
    has_server_key = False
    hint = ""
    try:
        if platform == "ozon":
            client_id = getattr(settings, "OZON_CLIENT_ID", "") or ""
            api_key = getattr(settings, "OZON_API_KEY", "") or ""
            has_server_key = bool(client_id.strip() and api_key.strip())
            if not has_server_key:
                hint = "Задайте OZON_CLIENT_ID и OZON_API_KEY в .env или введите данные в форме"
    except Exception as e:
        logger.warning(f"key-source check failed for {platform}: {e}")
        has_server_key = False

    return {"platform": platform, "has_server_key": has_server_key, "hint": hint}
