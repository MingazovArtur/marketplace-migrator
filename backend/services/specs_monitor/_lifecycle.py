"""Жизненный цикл записи задачи: queued → running → done; прогресс и сверка при старте воркера.

Вынесено без изменений из монолита services/specs_monitor.py (Р9).
"""

import logging

from services.cache_service import redis_client
from services.specs_monitor._keys import (
    ACTIVE_KEY,
    HISTORY_KEY,
    HISTORY_LEN,
    HISTORY_TTL,
    TASK_TTL,
    _dump,
    _load,
    _now,
    _task_key,
)
from services.specs_monitor._pause import clear_pause
from services.specs_monitor._queries import list_active

logger = logging.getLogger(__name__)


def register(
    task_id,
    platform: str,
    user_id: int,
    username: str = None,
    resume_params: dict | None = None,
) -> None:
    """
    Поставить задачу в реестр (state=queued). Вызывается в роутере сразу после delay().

    resume_params — всё, что нужно для повторного запуска задачи админом после
    паузы (enc_key/category_ids/business_id/skip_category_ids). enc_key — это
    зашифрованный ключ, тот же шифротекст, что уже лежит в сообщении Celery
    в этом же Redis (В-4, неделя 2); расшифровка — только в воркере.
    """
    if not redis_client or not task_id:
        return
    info = {
        "task_id": str(task_id),
        "platform": platform,
        "user_id": user_id,
        "username": username,
        "state": "queued",
        "enqueued_at": _now(),
        "started_at": None,
        "finished_at": None,
        "duration_ms": None,
        "status": None,
        "total": 0,
        "success": 0,
        "errors": 0,
        "message": None,
        "pause_requested": False,
        "done_keys": [],
        "resume_params": resume_params or {},
    }
    try:
        pipe = redis_client.pipeline()
        pipe.setex(_task_key(task_id), TASK_TTL, _dump(info))
        pipe.sadd(ACTIVE_KEY, str(task_id))
        pipe.execute()
    except Exception as e:
        logger.warning(f"specs_monitor.register({task_id}) не выполнен: {e}")


def set_running(task_id, platform: str = None, user_id: int = None, username: str = None) -> None:
    """Отметить задачу выполняемой (state=running). Создаёт запись, если роутер её не регистрировал."""
    if not redis_client or not task_id:
        return
    key = _task_key(task_id)
    try:
        info = _load(redis_client.get(key))
        if info is None:
            info = {
                "task_id": str(task_id),
                "enqueued_at": _now(),
                "started_at": None,
                "finished_at": None,
                "duration_ms": None,
                "status": None,
                "total": 0,
                "success": 0,
                "errors": 0,
                "message": None,
            }
        info["state"] = "running"
        info["started_at"] = info.get("started_at") or _now()
        if platform is not None:
            info["platform"] = platform
        if user_id is not None:
            info["user_id"] = user_id
        if username is not None:
            info["username"] = username

        pipe = redis_client.pipeline()
        pipe.setex(key, TASK_TTL, _dump(info))
        pipe.sadd(ACTIVE_KEY, str(task_id))
        pipe.execute()
    except Exception as e:
        logger.warning(f"specs_monitor.set_running({task_id}) не выполнен: {e}")


def finish(
    task_id,
    status: str,
    total: int = 0,
    success: int = 0,
    errors: int = 0,
    duration_ms: int = 0,
    message: str = None,
    done_keys: list[str] | None = None,
) -> None:
    """
    Завершить задачу: убрать из active, дописать итог, положить в history.

    status: success | partial | error | paused | interrupted.
    done_keys — категории, уже сохранённые в БД (нужно, чтобы resume
    продолжил с места остановки, а не начинал с нуля). При None —
    уже накопленные в инфо done_keys сохраняются (см. sync_done_keys).
    """
    if not redis_client or not task_id:
        return
    key = _task_key(task_id)
    try:
        info = _load(redis_client.get(key)) or {"task_id": str(task_id), "enqueued_at": _now()}
        if done_keys is not None:
            info["done_keys"] = [str(k) for k in done_keys]
        info["pause_requested"] = False
        info.update(
            {
                "task_id": str(task_id),
                "state": "done",
                "finished_at": _now(),
                "status": status,  # success | partial | error | paused
                "total": total,
                "success": success,
                "errors": errors,
                "duration_ms": duration_ms,
                "message": message,
            }
        )
        pipe = redis_client.pipeline()
        pipe.setex(key, TASK_TTL, _dump(info))
        pipe.srem(ACTIVE_KEY, str(task_id))
        pipe.lpush(HISTORY_KEY, _dump(info))
        pipe.ltrim(HISTORY_KEY, 0, HISTORY_LEN - 1)
        pipe.expire(HISTORY_KEY, HISTORY_TTL)
        pipe.execute()
    except Exception as e:
        logger.warning(f"specs_monitor.finish({task_id}) не выполнен: {e}")


def get_info(task_id) -> dict | None:
    """JSON-инфо задачи из реестра (None — задачи нет / Redis недоступен)."""
    if not redis_client or not task_id:
        return None
    try:
        return _load(redis_client.get(_task_key(task_id)))
    except Exception as e:
        logger.warning(f"specs_monitor.get_info({task_id}) не выполнен: {e}")
        return None


def sync_done_keys(task_id, done_keys) -> None:
    """
    Сохранить прогресс загрузки в реестр ПРЯМО ВО ВРЕМЯ выполнения.

    Вызывается задачей из progress_cb (раз в PROGRESS_EVERY категорий).
    Если воркер умрёт посреди загрузки (docker compose down, OOM),
    resume продолжит с последнего закоммиченного чанка, а не с нуля.
    Терминальные записи (done) и чужие задачи не трогаем.
    """
    if not redis_client or not task_id:
        return
    try:
        info = _load(redis_client.get(_task_key(task_id)))
        if info is None or info.get("state") == "done":
            return
        info["done_keys"] = [str(k) for k in done_keys]
        redis_client.setex(_task_key(task_id), TASK_TTL, _dump(info))
    except Exception as e:
        logger.warning(f"specs_monitor.sync_done_keys({task_id}) не выполнен: {e}")


def reconcile_on_startup(live=None) -> int:
    """
    Сверка реестра с реальностью при старте спек-воркера (сигнал worker_ready).

    Воркер с --pool=solo запускается без задач: значит, каждая запись
    state=running принадлежит задаче, убитой вместе с прошлым воркером
    (docker compose down / crash / OOM). Помечаем её interrupted —
    админ увидит «прервана» и продолжит с последнего сохранённого
    прогресса (done_keys синкаются в процессе загрузки).

    Записи в очереди (queued) НЕ трогаем: их сообщения могут лежать
    в брокере и будут выполнены (set_running поправит запись на старте).

    live — опциональный колбэк get_progress(task_id) -> dict, чтобы
    записать в историю последний живой прогресс (total/success/errors).
    Возвращает количество закрытых записей.
    """
    if not redis_client:
        return 0
    closed = 0
    try:
        for info in list_active():
            if info.get("state") != "running":
                continue
            task_id = info.get("task_id")
            total = success = errors = 0
            if live is not None:
                try:
                    p = live(task_id) or {}
                    total = int(p.get("total") or 0)
                    success = int(p.get("success") or 0)
                    errors = int(p.get("errors") or 0)
                except Exception:
                    pass
            clear_pause(task_id)
            finish(
                task_id,
                status="interrupted",
                total=total,
                success=success,
                errors=errors,
                message="Воркер был перезапущен — загрузка прервана, прогресс сохранён в БД",
            )
            closed += 1
        if closed:
            logger.info(f"specs_monitor.reconcile_on_startup: помечено прерванными {closed} записей")
    except Exception as e:
        logger.warning(f"specs_monitor.reconcile_on_startup() не выполнен: {e}")
    return closed
