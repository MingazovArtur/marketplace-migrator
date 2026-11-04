"""Фоновая загрузка спеков площадок (Ozon, Яндекс Маркет, Wildberries)."""

import contextlib
import logging
import time

from celery_app import celery_app
from database.repository import stats_repo
from services import cache_service
from tasks.matching import _spec_cache_invalidate

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.refresh_specs_task")
def refresh_specs_task(
    self,
    user_id: int,
    platform: str,
    raw_api_key: str,
    category_ids=None,
    business_id=None,
):
    """Единая фоновая загрузка спеков категорий площадки через её API с прогресс-баром."""
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
        raise

    t0 = time.perf_counter()
    logger.info(f"🚀 Старт загрузки спеков {platform} для пользователя {user_id}")

    def progress_cb(p: dict):
        try:
            total = p.get("total", 0)
            fetched = p.get("fetched", 0)
            errors = p.get("errors", 0)
            done = fetched + errors
            percent = int(done * 100 / total) if total else 0
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
                )
            )
        elif platform == "wildberries":
            result = asyncio.run(
                refresh_wildberries_specs(
                    user_id=user_id,
                    token=raw_api_key,
                    category_ids=category_ids,
                    progress_cb=progress_cb,
                )
            )
        else:
            raise ValueError(f"Загрузчик спеков для {platform} ещё не реализован")

        fetched = result.get("fetched", 0)
        errors = result.get("errors", 0)
        total = fetched + errors
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            f"✅ Спеки {platform} загружены: {fetched} категорий, {errors} ошибок за {duration_ms} мс"
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
