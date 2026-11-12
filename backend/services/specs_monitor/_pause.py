"""Пауза/возобновление загрузки спеков: флаги в Redis, защита от повторного resume.

Вынесено без изменений из монолита services/specs_monitor.py (Р9).
"""

import logging

from services.cache_service import redis_client
from services.specs_monitor._keys import (
    PAUSE_TTL,
    RESUMED_TTL,
    TASK_TTL,
    _dump,
    _load,
    _pause_key,
    _resumed_key,
    _task_key,
)

logger = logging.getLogger(__name__)


def request_pause(task_id) -> bool:
    """
    Админ просит паузу. Задача проверит флаг на старте / между блоками
    категорий и остановится сама (кооперативно). True — флаг установлен,
    False — задача не найдена или уже завершена.
    """
    if not redis_client or not task_id:
        return False
    key = _task_key(task_id)
    try:
        info = _load(redis_client.get(key))
        if info is None or info.get("state") == "done":
            return False
        info["pause_requested"] = True
        pipe = redis_client.pipeline()
        pipe.setex(key, TASK_TTL, _dump(info))
        pipe.setex(_pause_key(task_id), PAUSE_TTL, "1")
        pipe.execute()
        return True
    except Exception as e:
        logger.warning(f"specs_monitor.request_pause({task_id}) не выполнен: {e}")
        return False


def pause_requested(task_id) -> bool:
    """Проверить флаг паузы (вызывается задачей на старте и между блоками)."""
    if not redis_client or not task_id:
        return False
    try:
        return bool(redis_client.get(_pause_key(task_id)))
    except Exception as e:
        logger.warning(f"specs_monitor.pause_requested({task_id}) не выполнен: {e}")
        return False


def clear_pause(task_id) -> None:
    """Снять флаг паузы (задача его отработала / задача перезапущена)."""
    if not redis_client or not task_id:
        return
    try:
        redis_client.delete(_pause_key(task_id))
    except Exception as e:
        logger.warning(f"specs_monitor.clear_pause({task_id}) не выполнен: {e}")


def mark_resumed(old_task_id, new_task_id) -> None:
    """Запомнить, что остановленную задачу продолжила новая (защита от повторного resume)."""
    if not redis_client or not old_task_id:
        return
    try:
        redis_client.setex(_resumed_key(old_task_id), RESUMED_TTL, str(new_task_id))
    except Exception as e:
        logger.warning(f"specs_monitor.mark_resumed({old_task_id}) не выполнен: {e}")


def get_resumed(task_id) -> str | None:
    """id задачи-продолжения, если эта задача уже была продолжена."""
    if not redis_client or not task_id:
        return None
    try:
        raw = redis_client.get(_resumed_key(task_id))
        return raw.decode() if isinstance(raw, bytes) else raw
    except Exception as e:
        logger.warning(f"specs_monitor.get_resumed({task_id}) не выполнен: {e}")
        return None
