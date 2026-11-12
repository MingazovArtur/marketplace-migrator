"""Одиночная миграция товара (Celery, name="tasks.migrate_product_task")."""

import contextlib
import logging
import time

from celery_app import celery_app
from core.platforms import PLATFORM_CONFIG, PRICE_RULES
from database.repository import op_log, repo, stats_repo
from services import defaults_service
from services.platform_utils import detect_platform
from tasks.matching import (
    _base_source,
    _ensure_canonical_attributes,
    _pick_target_category,
    _safe_float,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Одиночная миграция
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="tasks.migrate_product_task")
def migrate_product_task(
    self, product_id: int, target_platform: str, user_id: int, edited_data: dict = None
):
    """
    Фоновая задача для одиночной миграции товара.
    Проверяет, что товар принадлежит user_id, перед обновлением.
    """
    t0 = time.perf_counter()
    final_price = None

    try:
        product = repo.get_by_id(product_id, user_id=user_id)
        if not product:
            logger.error(f"Товар {product_id} не найден или не принадлежит пользователю {user_id}")
            return {"status": "error", "message": "Товар не найден или не принадлежит вам"}

        previous_mapped_category = product.get("mapped_category")
        repo.update(product_id, {"status": "processing", "error_message": None}, user_id=user_id)

        old_price = _safe_float(product.get("price"))
        old_category = product.get("category")
        source_platform = detect_platform(product.get("source"))

        edited_category = edited_data.get("category") if edited_data else None
        target_category_name, how = _pick_target_category(
            product, edited_category, target_platform, user_id
        )
        if target_category_name:
            logger.info(
                f"📂 Товар {product_id}: категория '{target_category_name}' (источник: {how})"
            )

        # Дозаполнение пустой логистики и цены по умолчанию из дефолтов
        upd = defaults_service.build_updates_for_product(product, user_id)
        if upd:
            repo.update(product_id, upd, user_id=user_id)
            product.update(upd)
            logger.info(f"🩹 Товар {product_id}: дефолты дописали поля {list(upd)}")

        original_price = _safe_float(
            edited_data.get("price")
            if (edited_data and edited_data.get("price") is not None)
            else product.get("price")
        )
        price_multiplier = _safe_float(PRICE_RULES.get(target_platform, 1.0), default=1.0)
        final_price = round(original_price * price_multiplier, 2)

        if final_price <= 0:
            error_msg = (
                "Цена товара = 0 ₽. Укажите цену в поле «Цена, ₽» в этом окне "
                "(или массово: «Обновить цену/бренд» в таблице товаров) и повторите миграцию."
            )
            repo.update(
                product_id,
                {
                    "status": "error",
                    "error_message": error_msg,
                },
                user_id=user_id,
            )
            logger.warning(f"⚠️ Товар {product_id}: миграция отклонена — цена 0")
            return {"status": "error", "message": error_msg, "product_id": product_id}

        final_name = (
            edited_data.get("name")
            if (edited_data and edited_data.get("name"))
            else product.get("name")
        )
        base_source = _base_source(product.get("source"))
        new_source = f"{base_source} → {PLATFORM_CONFIG[target_platform]['name']}"

        if target_category_name is None:
            error_msg = (
                f"Не найдена точная категория в спеках {target_platform} для товара '{final_name}'. "
                f"Выберите категорию в модалке миграции из выпадающего списка "
                f"(формат «Родитель / Тип», например «Одежда / Футболка») "
                f"или задайте её в разделе «Маппинг». Список имён — на странице «Спецификации»."
            )
            repo.update(
                product_id,
                {
                    "status": "error",
                    "name": final_name,
                    "price": final_price,
                    "mapped_category": previous_mapped_category,
                    "error_message": error_msg,
                },
                user_id=user_id,
            )
            logger.warning(f"⚠️ Товар {product_id}: {error_msg}")
            return {"status": "error", "message": error_msg, "product_id": product_id}

        # Авто-дозаполнение обязательных атрибутов XLS-шаблона ДО обновления статуса
        _ensure_canonical_attributes(
            product_id=product_id,
            target_platform=target_platform,
            target_category_name=target_category_name,
            product_name=final_name or product.get("name"),
            okpd_code=product.get("okpd_code"),
            user_id=user_id,
        )

        repo.update(
            product_id,
            {
                "status": "success",
                "source": new_source,
                "name": final_name,
                "price": final_price,
                "mapped_category": target_category_name,
                "error_message": None,
            },
            user_id=user_id,
        )

        duration_ms = int((time.perf_counter() - t0) * 1000)
        stats_repo.record(
            user_id=user_id,
            operation="migrate",
            platform=target_platform,
            status="success",
            total_items=1,
            success_items=1,
            duration_ms=duration_ms,
        )
        op_log.log_migration(
            user_id=user_id,
            product_id=product_id,
            product_name=final_name,
            source_platform=source_platform,
            target_platform=target_platform,
            old_price=old_price,
            new_price=final_price,
            old_category=old_category,
            new_category=target_category_name,
            status="success",
            error_message=None,
            is_batch=False,
            batch_id=self.request.id,
        )
        logger.info(
            f"✅ Товар {product_id} мигрирован (цена: {old_price} → {final_price}, "
            f"категория: {target_category_name})"
        )
        return {"status": "completed", "product_id": product_id}

    except Exception as e:
        logger.error(f"❌ Ошибка миграции товара {product_id}: {e}", exc_info=True)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        with contextlib.suppress(Exception):
            repo.update(product_id, {"status": "error", "error_message": str(e)}, user_id=user_id)
        with contextlib.suppress(Exception):
            stats_repo.record(
                user_id=user_id,
                operation="migrate",
                platform=target_platform,
                status="error",
                total_items=1,
                failed_items=1,
                duration_ms=duration_ms,
            )
        with contextlib.suppress(Exception):
            op_log.log_migration(
                user_id=user_id,
                product_id=product_id,
                product_name=None,
                source_platform=None,
                target_platform=target_platform,
                status="error",
                error_message=str(e),
                is_batch=False,
                batch_id=self.request.id,
            )
        return {"status": "error", "message": str(e)}
