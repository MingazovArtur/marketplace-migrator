"""
Реестр загрузок спеков площадок для админ-мониторинга.

Проблема: refresh_specs_task крутится в воркере с --pool=solo — параллельные
загрузки стоят в очереди Redis, и снаружи (кроме запустившего пользователя
с его task_id) их не видно. Этот модуль ведёт в Redis реестр всех загрузок:

  specs:task:{task_id}   JSON-инфо задачи (TTL 24 ч — после падения воркера
                         «зависшая» запись исчезает сама, реестр не гниёт)
  specs:tasks:active     SET id задач в очереди / в работе
  specs:tasks:history    LIST последних завершённых (обрезается до 50, TTL 7 дней)

Пауза/возобновление (админ, кооперативная остановка):
  specs:pause:{task_id}  флаг «админ просил паузу» — задача сама проверяет его
                         на старте и между блоками категорий; снявшись, очищает
                         флаг и сохраняет в инфо done_keys (обработанные
                         категории) — их resume пропускает
  specs:resumed:{old}    id новой задачи, которой продолжили старую (TTL 7 дней)

Жёсткий перезапуск воркера (docker compose down, OOM, crash):
  sync_done_keys()      задача периодически (в progress_cb) сохраняет в реестр
                         ключи уже закоммиченных категорий — после гибели
                         воркера resume продолжит с последнего чанка, не с нуля
  reconcile_on_startup() на старте спек-воркера (pool=solo — на старте ни одна
                         задача выполняться не может) помечает все running-записи
                         статусом interrupted; админ видит «прервана» и
                         может продолжить с сохранённого прогресса

Публичный API (все функции безопасны без Redis — мониторинг отключается,
на сами задачи это не влияет):
  - register(task_id, platform, user_id, username, resume_params) — роутер, при постановке в очередь
  - set_running(task_id, ...)                       — задача, в начале выполнения
  - finish(task_id, status, ..., done_keys)         — задача, в конце (success/partial/error/paused/interrupted)
  - sync_done_keys(task_id, done_keys)              — задача, в процессе (прогресс для resume)
  - reconcile_on_startup(live)                      — сигнал worker_ready спек-воркера
  - list_active() / list_history(limit)             — чтение для /api/admin/specs-tasks
  - is_stale(info, live_percent)                    — running без прогресса > 15 мин
  - request_pause(task_id) / pause_requested(task_id) / clear_pause(task_id)
  - get_info(task_id) / mark_resumed(old_id, new_id) / get_resumed(task_id)
"""

import json
import logging
import time

from services.cache_service import redis_client

logger = logging.getLogger(__name__)

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


# ==================== Пауза / возобновление ====================


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
