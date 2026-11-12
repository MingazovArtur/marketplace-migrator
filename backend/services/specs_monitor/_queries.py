"""Чтение реестра для UI: активные задачи, история, детект «зависшей» задачи.

Вынесено без изменений из монолита services/specs_monitor.py (Р9).
"""

import logging

from services.cache_service import redis_client
from services.specs_monitor._keys import (
    ACTIVE_KEY,
    HISTORY_KEY,
    STALE_RUNNING_SEC,
    _load,
    _now,
    _task_key,
)
from services.specs_monitor._pause import get_resumed

logger = logging.getLogger(__name__)


def list_active() -> list[dict]:
    """Активные (queued/running) задачи, свежие сверху. Пропускает протухшие ключи."""
    if not redis_client:
        return []
    try:
        ids = [i for i in redis_client.smembers(ACTIVE_KEY) if i]
        if not ids:
            return []
        raw = redis_client.mget([_task_key(i) for i in ids])
        out = [x for x in (_load(r) for r in raw) if x]
        out.sort(key=lambda x: x.get("enqueued_at") or 0, reverse=True)
        return out
    except Exception as e:
        logger.warning(f"specs_monitor.list_active() не выполнен: {e}")
        return []


def list_history(limit: int = 20) -> list[dict]:
    """Последние завершённые загрузки (свежие сверху) + отметка resumed_as."""
    if not redis_client:
        return []
    try:
        raw = redis_client.lrange(HISTORY_KEY, 0, max(0, limit - 1))
        out = [x for x in (_load(r) for r in raw) if x]
        for info in out:
            resumed_as = get_resumed(info.get("task_id"))
            if resumed_as:
                info["resumed_as"] = resumed_as
        return out
    except Exception as e:
        logger.warning(f"specs_monitor.list_history() не выполнен: {e}")
        return []


def is_stale(info: dict, live_percent: int = 0) -> bool:
    """running-задача без прогресса дольше STALE_RUNNING_SEC — вероятно, воркер перезапущен."""
    if not isinstance(info, dict) or info.get("state") != "running":
        return False
    started = info.get("started_at") or info.get("enqueued_at") or 0
    return (_now() - started) > STALE_RUNNING_SEC and not live_percent
