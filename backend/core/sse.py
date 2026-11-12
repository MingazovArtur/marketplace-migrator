"""
SSE-стриминг состояния фоновых задач (замена polling'а с фронта).

Кадр — JSON того же формата, что и у соответствующего polling-эндпоинта:
    data: {"status": "progress", "total": 100, "done": 42, "percent": 42, ...}

Правила потока:
  - первый снимок отдаётся сразу (без паузы) — клиент мгновенно видит статус;
  - источник (Celery/БД — блокирующий) опрашивается каждые POLL_SECONDS
    в threadpool'е (event loop не блокируется);
  - снимок уходит клиенту только если изменился; если молчание затягивается
    дольше HEARTBEAT_SECONDS — шлётся SSE-комментарий `: keepalive`, чтобы
    прокси (nginx proxy_read_timeout 300s) не рвал «молчащий» поток;
  - терминальный статус (completed/failed/paused/…) шлётся всегда и закрывает
    поток — клиент не переподключается;
  - поток самозакрывается по MAX_STREAM_SECONDS («вечных» соединений нет):
    клиент переподключается сам (EventSource-семантика — см. api/sse.js);
  - ошибка чтения ПЕРВОГО снимка — исключение наружу (эндпоинт возвращает
    честный 5xx, как его polling-близнец), ошибка последующих — warning
    и повтор через такт: поток переживает моргание Redis/Celery, не роняя
    соединение.

Тайминги — константы модуля, а не значения по умолчанию в сигнатуре:
эндпоинты их не дублируют, тесты подменяют monkeypatch'ем (иначе SSE-тест
спал бы секунды на реальных интервалах).
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Частота опроса источника (сек) — как у polling'а, который SSE заменяет
POLL_SECONDS = 1.0
# Предел молчания потока (сек): дольше — keepalive-комментарий
HEARTBEAT_SECONDS = 15.0
# Потолок жизни одного соединения (сек); потоки без терминального статуса
# (например, мониторинг спеков) закрываются по нему, фронт переподключается
MAX_STREAM_SECONDS = 600.0

# Заголовки SSE-ответа: X-Accel-Buffering отключает буферизацию в nginx
# (иначе кадры копятся в буфере прокси и приходят пачкой по закрытию задачи)
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _frame(payload: dict) -> str:
    """Один SSE-кадр: строка `data: ...` + пустая строка (конец кадра)."""
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _canonical(payload: dict) -> str:
    """Канонический JSON для сравнения снимков (дедуп без изменения формата)."""
    return json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)


async def task_events(
    fetch_state: Callable[[], dict],
    *,
    terminal: frozenset[str],
    initial: dict | None = None,
    poll_seconds: float | None = None,
    heartbeat_seconds: float | None = None,
    max_seconds: float | None = None,
):
    """
    Async-генератор SSE-кадров состояния задачи.

    fetch_state  — синхронная функция снимка (Celery/БД), выполняется
                   в threadpool'е;
    terminal     — статусы, на которых поток закрывается;
    initial      — заранее снятый первый снимок (эндпоинт сам делает первый
                   запрос, чтобы его ошибка вернула честный 5xx ещё до старта
                   потока; без initial первый снимок делает генератор).
    """
    poll = POLL_SECONDS if poll_seconds is None else poll_seconds
    heartbeat = HEARTBEAT_SECONDS if heartbeat_seconds is None else heartbeat_seconds
    max_wait = MAX_STREAM_SECONDS if max_seconds is None else max_seconds

    started = time.monotonic()

    # --- первый снимок: мгновенно, до любого sleep'а ---
    state = initial if initial is not None else await asyncio.to_thread(fetch_state)
    yield _frame(state)
    if state.get("status") in terminal:
        return

    last_sent = _canonical(state)
    last_output = time.monotonic()

    # --- цикл: опрос → дедуп → кадр; keepalive при молчании ---
    while True:
        await asyncio.sleep(poll)

        # До следующего возможного кадра молчание превысит heartbeat —
        # сигнал прокси, что соединение живо
        if time.monotonic() - last_output + poll > heartbeat:
            yield ": keepalive\n\n"
            last_output = time.monotonic()

        if time.monotonic() - started >= max_wait:
            logger.info("SSE: поток закрыт по лимиту времени (%.0f с)", max_wait)
            return

        try:
            state = await asyncio.to_thread(fetch_state)
        except Exception as e:  # noqa: BLE001 — разовый сбой не роняет поток
            logger.warning("SSE: не удалось снять состояние задачи: %s", e)
            continue

        if state.get("status") in terminal:
            yield _frame(state)
            return

        canonical = _canonical(state)
        if canonical != last_sent:
            yield _frame(state)
            last_sent = canonical
            last_output = time.monotonic()
