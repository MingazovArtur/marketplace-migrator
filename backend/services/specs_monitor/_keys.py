"""Ключи Redis, TTL и сериализация записей реестра спеков.

Вынесено без изменений из монолита services/specs_monitor.py (Р9).
"""

import json
import time

# Статусы, которые можно продолжить кнопкой «Возобновить»
RESUMABLE_STATUSES = ("paused", "interrupted")

_TASK_KEY = "specs:task:{task_id}"
ACTIVE_KEY = "specs:tasks:active"
HISTORY_KEY = "specs:tasks:history"
PAUSE_KEY = "specs:pause:{task_id}"
RESUMED_KEY = "specs:resumed:{task_id}"
TASK_TTL = 24 * 3600  # 24 часа
HISTORY_LEN = 50
HISTORY_TTL = 7 * 24 * 3600  # 7 дней
PAUSE_TTL = 24 * 3600  # флаг живёт столько же, сколько запись задачи
RESUMED_TTL = 7 * 24 * 3600  # ссылка «эта задача продолжена новой» — как история
STALE_RUNNING_SEC = 15 * 60  # running без прогресса дольше 15 минут — воркер, вероятно, умер


def _now() -> float:
    return time.time()


def _task_key(task_id) -> str:
    return _TASK_KEY.format(task_id=task_id)


def _load(raw):
    """Безопасный парс JSON-записи задачи."""
    try:
        info = json.loads(raw) if isinstance(raw, str) else raw
        return info if isinstance(info, dict) else None
    except Exception:
        return None


def _dump(info: dict) -> str:
    return json.dumps(info, ensure_ascii=False)


def _pause_key(task_id) -> str:
    return PAUSE_KEY.format(task_id=task_id)


def _resumed_key(task_id) -> str:
    return RESUMED_KEY.format(task_id=task_id)
