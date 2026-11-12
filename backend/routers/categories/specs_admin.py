"""
Админ-мониторинг загрузок спеков: список активных/завершённых, пауза, возобновление.

Вынесено без изменений из монолита routers/categories.py (Р7).
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from core.auth import get_current_user
from core.sse import SSE_HEADERS, task_events
from database.models import User
from routers.categories._support import _public_task_info, _require_admin
from services import specs_monitor
from tasks import get_progress, refresh_specs_task

logger = logging.getLogger(__name__)
router = APIRouter()

# Частота опроса реестра в SSE-потоке мониторинга (сек) — как был polling страницы
MONITOR_POLL_SECONDS = 3.0


def _admin_snapshot() -> dict:
    """Снимок мониторинга (активные + история) — общее для GET и SSE-эндпоинта."""
    active = []
    for info in specs_monitor.list_active():
        live = get_progress(info.get("task_id", ""))
        live_percent = int(live.get("percent") or 0)
        in_progress = live.get("status") == "progress"
        pause_requested = bool(info.get("pause_requested"))
        active.append(
            {
                "task_id": info.get("task_id"),
                "platform": info.get("platform"),
                "user_id": info.get("user_id"),
                "username": info.get("username"),
                "state": "running" if in_progress else info.get("state"),
                "enqueued_at": info.get("enqueued_at"),
                "started_at": info.get("started_at"),
                "percent": live_percent if in_progress else 0,
                "total": live.get("total", 0) if in_progress else 0,
                "success": live.get("success", 0) if in_progress else 0,
                "errors": live.get("errors", 0) if in_progress else 0,
                "stale": specs_monitor.is_stale(info, live_percent),
                "pause_requested": pause_requested,
                "can_pause": not pause_requested,
            }
        )

    history = []
    for info in specs_monitor.list_history(20):
        info = _public_task_info(info)
        info["can_resume"] = info.get(
            "status"
        ) in specs_monitor.RESUMABLE_STATUSES and not info.get("resumed_as")
        history.append(info)

    return {
        "success": True,
        "active": active,
        "history": history,
    }


@router.get("/admin/specs-tasks")
def admin_specs_tasks(current_user: User = Depends(get_current_user)):
    """
    Мониторинг загрузок спеков (только админ).

    Активные (в очереди / в работе) с живым прогрессом из Celery
    + последние завершённые (успех/ошибки/длительность/пауза).
    """
    _require_admin(current_user)
    return _admin_snapshot()


@router.get("/admin/specs-tasks/events")
async def admin_specs_tasks_events(current_user: User = Depends(get_current_user)):
    """
    SSE-мониторинг загрузок спеков (только админ): снимок пушем при изменении.

    Кадр — тот же JSON, что у GET /admin/specs-tasks. Терминального статуса нет
    (мониторинг бесконечен): поток закрывается по лимиту времени core/sse.py,
    фронт переподключается сам (api/sse.js). Первый снимок снимается здесь,
    а не в генераторе, чтобы его ошибка (Redis/Celery) вернула честный 5xx.
    """
    _require_admin(current_user)
    first = await asyncio.to_thread(_admin_snapshot)
    return StreamingResponse(
        task_events(
            _admin_snapshot,
            terminal=frozenset(),
            initial=first,
            poll_seconds=MONITOR_POLL_SECONDS,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/admin/specs-tasks/{task_id}/pause")
def admin_specs_task_pause(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Поставить загрузку спеков на паузу (только админ).

    Кооперативная остановка: задача проверяет флаг между блоками категорий,
    дообрабатывает текущий блок (прогресс коммитится в БД) и завершается
    со статусом paused. Стоящая в очереди задача снимается на старте —
    воркер освобождается для других работ. Возобновление — POST .../{task_id}/resume.
    """
    _require_admin(current_user)

    if not specs_monitor.request_pause(task_id):
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена или уже завершена",
        )
    logger.info(f"⏸ ADMIN PAUSE SPECS: user={current_user.id} task={task_id}")
    return {
        "success": True,
        "task_id": task_id,
        "message": (
            "Пауза запрошена: задача остановится после текущего блока категорий "
            "(стоящая в очереди — на старте). Продолжить можно кнопкой «Возобновить»"
        ),
    }


@router.post("/admin/specs-tasks/{task_id}/resume")
def admin_specs_task_resume(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Продолжить остановленную загрузку спеков (только админ).

    Работает и для «на паузе», и для «прервана» (воркер был перезапущен —
    docker compose down / crash: при старте спек-воркера такие записи
    помечаются interrupted, а прогресс закоммиченных категорий
    сохраняется в реестр во время загрузки). Ставит в очередь НОВУЮ задачу
    с теми же параметрами (ключ берётся из реестра — повторный ввод не нужен)
    и списком уже сохранённых категорий (skip_category_ids): загрузка
    продолжается с места остановки.
    """
    _require_admin(current_user)

    info = specs_monitor.get_info(task_id)
    if not info:
        raise HTTPException(status_code=404, detail="Задача не найдена в реестре мониторинга")
    if info.get("status") not in specs_monitor.RESUMABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Продолжить можно только задачу «на паузе» или «прерванную» "
            "(например, после перезапуска воркера)",
        )
    if specs_monitor.get_resumed(task_id):
        raise HTTPException(status_code=409, detail="Эта задача уже была продолжена")

    params = info.get("resume_params") or {}
    enc_key = params.get("enc_key")
    platform = info.get("platform")
    user_id = info.get("user_id")
    if not enc_key or not platform or not user_id:
        raise HTTPException(
            status_code=409,
            detail="Параметры запуска не сохранились (задача запущена до обновления) — "
            "запустите загрузку заново на странице «Спецификации»",
        )

    # Что уже в БД: категории этой загрузки + унаследованные из предыдущих поколений
    skip = sorted(
        {str(k) for k in (info.get("done_keys") or [])}
        | {str(k) for k in (params.get("skip_category_ids") or [])}
    )

    try:
        task = refresh_specs_task.delay(
            user_id=user_id,
            platform=platform,
            raw_api_key=enc_key,
            category_ids=params.get("category_ids"),
            business_id=params.get("business_id"),
            skip_category_ids=skip,
        )
    except Exception as e:
        logger.error(f"❌ Не удалось поставить продолжение задачи {task_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Не удалось поставить задачу в очередь: {e}")

    specs_monitor.register(
        task.id,
        platform=platform,
        user_id=user_id,
        username=info.get("username"),
        resume_params={
            "enc_key": enc_key,
            "category_ids": params.get("category_ids"),
            "business_id": params.get("business_id"),
            "skip_category_ids": skip,
        },
    )
    specs_monitor.mark_resumed(task_id, task.id)

    logger.info(
        f"▶ ADMIN RESUME SPECS: user={current_user.id} old_task={task_id} -> new_task={task.id} "
        f"[{platform}] пропустить {len(skip)} категорий"
    )
    return {
        "success": True,
        "task_id": task.id,
        "platform": platform,
        "skipped": len(skip),
        "message": f"Загрузка продолжена (пропущено уже сохранённых категорий: {len(skip)}). "
        "Новая задача видна в списке активных.",
    }
