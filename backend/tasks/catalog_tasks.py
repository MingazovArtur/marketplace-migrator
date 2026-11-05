"""Фоновая загрузка спеков площадок (Ozon, Яндекс Маркет, Wildberries)."""

import contextlib
import logging
import os
import time

from celery_app import celery_app
from celery.signals import worker_ready
from database.repository import stats_repo
from services import cache_service, specs_monitor
from tasks.matching import _spec_cache_invalidate
from tasks.progress import get_progress

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.refresh_specs_task")
def refresh_specs_task(
    self,
    user_id: int,
    platform: str,
    raw_api_key: str,
    category_ids=None,
    business_id=None,
    skip_category_ids=None,
):
    """
    Единая фоновая загрузка спеков категорий площадки через её API с прогресс-баром.

    skip_category_ids — ключи категорий, уже сохранённых в БД (задача-продолжение
    после паузы, см. POST /api/admin/specs-tasks/{task_id}/resume).
    """
    import asyncio

    from core.crypto import decrypt_str
    from services.ozon_specs import refresh_ozon_specs
    from services.wb_specs import refresh_wildberries_specs
    from services.yandex_specs import refresh_yandex_specs

    # В-4 (неделя 2): ключ пришёл через Redis зашифрованным (enc1:...).
    # Legacy-задачи из очереди до деплоя содержат plaintext — decrypt_str
    # пропустит их как есть. Повреждённый/чужой токен — громкий падёж задачи.
    try:
        raw_api_key = decrypt_str(raw_api_key)
    except ValueError as e:
        logger.error(f"❌ Не удалось расшифровать API-ключ (задача {self.request.id}): {e}")
        # Реестр мониторинга: задача стартовала и сразу упала — закрываем запись,
        # иначе она навсегда осталась бы в списке активных (queued)
        specs_monitor.finish(
            self.request.id, status="error", message=f"Не удалось расшифровать API-ключ: {e}"
        )
        raise

    t0 = time.perf_counter()
    logger.info(f"🚀 Старт загрузки спеков {platform} для пользователя {user_id}")
    # Реестр мониторинга (админ-страница): queued -> running
    specs_monitor.set_running(self.request.id, platform=platform, user_id=user_id)

    # Пауза могла быть запрошена, пока задача стояла в очереди: воркер solo,
    # сообщение уже из Redis не вернуть — снимаемся сразу, не тратя API-лимиты
    if specs_monitor.pause_requested(self.request.id):
        logger.info(f"⏸ Задача {self.request.id} остановлена на старте (пауза из очереди)")
        specs_monitor.clear_pause(self.request.id)
        specs_monitor.finish(
            self.request.id,
            status="paused",
            message="Поставлена на паузу, пока стояла в очереди",
        )
        return {
            "status": "paused",
            "platform": platform,
            "total": 0,
            "done": 0,
            "success": 0,
            "errors": 0,
            "percent": 0,
        }

    # Ключи успешно сохранённых категорий: при паузе пишутся в реестр,
    # задача-продолжение пропустит их через skip_category_ids
    done_keys: set[str] = set(skip_category_ids or [])

    def pause_requested_now() -> bool:
        return specs_monitor.pause_requested(self.request.id)

    def progress_cb(p: dict):
        try:
            total = p.get("total", 0)
            fetched = p.get("fetched", 0)
            errors = p.get("errors", 0)
            done = fetched + errors
            percent = int(done * 100 / total) if total else 0
            # Прогресс для resume: ключи закоммиченных категорий пишем в реестр
            # прямо во время загрузки — если воркер умрёт (docker compose down,
            # OOM), продолжение уйдёт не с нуля, а с последнего чанка.
            # Вызывается раз в PROGRESS_EVERY категорий — дёшево.
            if done_keys:
                specs_monitor.sync_done_keys(self.request.id, done_keys)
            self.update_state(
                state="PROGRESS",
                meta={
                    "total": total,
                    "done": done,
                    "success": fetched,
                    "errors": errors,
                    "percent": percent,
                    "platform": platform,
                    "error_details": [],
                },
            )
        except Exception as e:
            logger.warning(f"Не удалось опубликовать прогресс спеков: {e}")

    try:
        if platform == "ozon":
            result = asyncio.run(
                refresh_ozon_specs(
                    user_id=user_id,
                    raw_api_key=raw_api_key,
                    category_ids=category_ids,
                    progress_cb=progress_cb,
                    skip_category_ids=skip_category_ids,
                    pause_check=pause_requested_now,
                    done_keys=done_keys,
                )
            )
        elif platform == "yandex":
            result = asyncio.run(
                refresh_yandex_specs(
                    user_id=user_id,
                    token=raw_api_key,
                    business_id=business_id,
                    category_ids=category_ids,
                    progress_cb=progress_cb,
                    skip_category_ids=skip_category_ids,
                    pause_check=pause_requested_now,
                    done_keys=done_keys,
                )
            )
        elif platform == "wildberries":
            result = asyncio.run(
                refresh_wildberries_specs(
                    user_id=user_id,
                    token=raw_api_key,
                    category_ids=category_ids,
                    progress_cb=progress_cb,
                    skip_category_ids=skip_category_ids,
                    pause_check=pause_requested_now,
                    done_keys=done_keys,
                )
            )
        else:
            raise ValueError(f"Загрузчик спеков для {platform} ещё не реализован")

        fetched = result.get("fetched", 0)
        errors = result.get("errors", 0)
        total = fetched + errors
        duration_ms = int((time.perf_counter() - t0) * 1000)

        # ⏸ Админ остановил загрузку: сохраняем прогресс в реестр (done_keys),
        # частично загруженные спеки уже в БД — сбрасываем кэши как обычно
        if result.get("paused"):
            logger.info(
                f"⏸ Загрузка спеков {platform} поставлена на паузу: "
                f"обработано {total}, из них сохранено {fetched}"
            )
            specs_monitor.clear_pause(self.request.id)
            specs_monitor.finish(
                self.request.id,
                status="paused",
                total=total,
                success=fetched,
                errors=errors,
                duration_ms=duration_ms,
                message="Поставлена на паузу администратором",
                done_keys=sorted(done_keys),
            )
            cache_service.delete_pattern(f"specs:{platform}:*")
            cache_service.delete_pattern(f"categories:{platform}:*")
            _spec_cache_invalidate(platform)
            return {
                "status": "paused",
                "platform": platform,
                "total": total,
                "done": total,
                "success": fetched,
                "fetched": fetched,
                "errors": errors,
                "percent": 0,
                "message": "Загрузка поставлена на паузу администратором",
            }

        logger.info(
            f"✅ Спеки {platform} загружены: {fetched} категорий, {errors} ошибок за {duration_ms} мс"
        )
        # Реестр мониторинга: running -> done (итог виден админу на странице мониторинга)
        specs_monitor.finish(
            self.request.id,
            status="success" if errors == 0 else "partial",
            total=total,
            success=fetched,
            errors=errors,
            duration_ms=duration_ms,
        )
        cache_service.delete_pattern(f"specs:{platform}:*")
        cache_service.delete_pattern(f"categories:{platform}:*")
        # P-3: сбрасываем in-process кэш имён/спеков в воркерах,
        # чтобы миграции сразу видели свежий справочник
        _spec_cache_invalidate(platform)

        try:
            stats_repo.record(
                user_id=user_id,
                operation="specs_refresh",
                platform=platform,
                status="success" if errors == 0 else "partial",
                total_items=total,
                success_items=fetched,
                failed_items=errors,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.warning(f"Не удалось записать статистику спеков: {e}")

        return {
            "status": "completed",
            "platform": platform,
            "total": total,
            "done": total,
            "success": fetched,
            "fetched": fetched,
            "errors": errors,
            "percent": 100,
            "error_details": result.get("error_details", []),
            "duration_ms": duration_ms,
        }

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки спеков {platform}: {e}", exc_info=True)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        specs_monitor.finish(
            self.request.id,
            status="error",
            message=str(e)[:500],
            duration_ms=duration_ms,
        )
        with contextlib.suppress(Exception):
            stats_repo.record(
                user_id=user_id,
                operation="specs_refresh",
                platform=platform,
                status="error",
                total_items=0,
                failed_items=1,
                duration_ms=duration_ms,
            )
        return {
            "status": "error",
            "platform": platform,
            "total": 0,
            "done": 0,
            "success": 0,
            "errors": 1,
            "percent": 0,
            "message": str(e),
            "error_details": [{"error": str(e)}],
        }


# ==================== Сверка реестра при старте спек-воркера ====================


@worker_ready.connect
def _reconcile_specs_registry_on_worker_start(sender=None, **kwargs):
    """
    Спек-воркер только что стартовал (--pool=solo) — значит, ни одна загрузка
    спеков сейчас не выполняется. Все записи реестра в state=running —
    «трупы» задач, убитых вместе с прошлым воркером (docker compose down,
    crash, OOM): помечаем их «прервана», чтобы админ мог продолжить
    с последнего сохранённого прогресса.

    Работает только в контейнере спек-воркера (env SPECS_WORKER=1): обычный
    и xlsx-воркеры при старте ничего не помечают (иначе перезапуск соседа
    ложно «прерывал» бы живую загрузку).
    """
    if os.getenv("SPECS_WORKER") != "1":
        return
    try:
        closed = specs_monitor.reconcile_on_startup(live=get_progress)
        if closed:
            logger.info(
                f"⏸ Старт спек-воркера: {closed} записей мониторинга помечено «прервана» "
                "(задачи убиты перезапуском воркера)"
            )
    except Exception as e:
        logger.warning(f"Сверка реестра спеков при старте воркера не выполнена: {e}")
