"""
Общая инфраструктура экспорта: IDOR-реестр владельцев фоновых задач,
content-disposition для русских имён файлов, парсинг списков id, константы.

Вынесено из монолита routers/export.py (Р1, разбиение на пакет):
роутеры импортируют отсюда только то, что не относится к HTTP-слою.
"""

import logging
import os
from urllib.parse import quote

import redis
from fastapi import HTTPException

from celery_app import celery_app
from core.config import settings
from database.models import User

logger = logging.getLogger(__name__)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Порог количества товаров, начиная с которого сборка XLSX автоматически уходит в очередь xlsx_export
CELERY_XLSX_THRESHOLD = int(os.getenv("CELERY_XLSX_THRESHOLD", "30"))
CELERY_XLSX_TIMEOUT_SEC = int(os.getenv("CELERY_XLSX_TIMEOUT_SEC", "180"))

# --- IDOR-защита фоновых задач экспорта (было В-2 код-ревью) ---
# Реестр владельцев task_id: без него любой авторизованный пользователь
# мог скачать чужой XLSX/ZIP, зная/подобрав task_id.
_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
EXPORT_TASK_TTL_SEC = 24 * 3600  # ключ живёт столько же, сколько файл в /media/exports


def register_export_task_owner(task_id: str, user_id: int) -> None:
    """Привязка задачи к владельцу (вызывается сразу после apply_async)."""
    try:
        _redis.setex(f"export_task_owner:{task_id}", EXPORT_TASK_TTL_SEC, str(user_id))
    except Exception as e:
        # Не критично: fallback-проверка по user_id в результате задачи
        logger.warning(f"Не удалось записать владельца задачи {task_id}: {e}")


def assert_export_task_owner(task_id: str, current_user: User) -> None:
    """
    Задача экспорта должна принадлежать current_user (админ — исключение).
    Чужая задача выглядит как несуществующая (404, без раскрытия факта).
    """
    if getattr(current_user, "role", None) == "admin":
        return

    owner = None
    try:
        owner = _redis.get(f"export_task_owner:{task_id}")
    except Exception as e:
        logger.warning(f"Redis недоступен при проверке владельца задачи {task_id}: {e}")

    if owner is not None:
        if str(owner) == str(current_user.id):
            return
        raise HTTPException(status_code=404, detail="Задача не найдена")

    # Ключа нет (Redis чистился или задача создана до этого патча):
    # для завершённых задач проверяем user_id, который воркер кладёт в результат.
    res = celery_app.AsyncResult(task_id)
    if res.ready() and res.successful() and isinstance(res.result, dict):
        owner_id = res.result.get("user_id")
        if owner_id is not None and str(owner_id) == str(current_user.id):
            return

    raise HTTPException(status_code=404, detail="Задача не найдена")


def safe_disposition(filename: str) -> str:
    ascii_name = "".join(c if ord(c) < 128 else "_" for c in filename).strip("_") or "export.xlsx"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def parse_product_ids(product_id: int | None, product_ids: str | None) -> list[int]:
    ids: list[int] = []
    if product_id is not None and product_id > 0:
        ids.append(int(product_id))
    if product_ids:
        for part in str(product_ids).split(","):
            part = part.strip()
            if part.isdigit() and int(part) > 0:
                val = int(part)
                if val not in ids:
                    ids.append(val)
    return ids
