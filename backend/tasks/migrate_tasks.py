"""Одиночная и пакетная миграция товаров (Celery)."""

import contextlib
import logging
import time
from datetime import datetime

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


# ---------------------------------------------------------------------------
# Пакетная миграция
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="tasks.migrate_batch_task")
def migrate_batch_task(self, product_ids: list, target_platform: str, user_id: int):
    """
    Пакетная миграция товаров с отслеживанием прогресса и журналом.

    P-3 (неделя 3) — было ~8 сессий БД и ~4 commit'а на КАЖДЫЙ товар
    (get_by_id, _spec_name_exists ×N, _match_spec_by_text с выгрузкой ВСЕХ
    имён категорий, _load_spec_for_category, дефолты, статус, журнал,
    прогресс в Redis на каждый шаг). Стало:
      * статус processing — ОДИН bulk-запрос на весь пакет;
      * товары — пакетная выборка чанками по 100 (repo.get_by_ids);
      * имена/спеки категорий — из in-process TTL-кэша (_spec_cache_*);
      * финальные статусы — одним repo.update_batch (1 сессия/commit на пакет);
      * журнал миграций — bulk insert чанками по 200 (log_migration_batch);
      * прогресс в Redis — не чаще ~одного раза на 5% пакета.
    """
    t0 = time.perf_counter()
    total = len(product_ids)
    success_count = 0
    error_count = 0
    errors = []
    status_updates: list = []  # [(product_id, {колонки})] — применяется батчем в конце
    log_entries: list = []     # dicts для MigrationLog — bulk insert в конце

    def _publish(done: int, force: bool = False):
        """Прогресс в Redis с троттлингом (P-3): ~1 запись на 5% или 25 товаров."""
        percent = int(done * 100 / total) if total else 0
        if (
            not force
            and percent - _publish.last_percent < 5
            and done - _publish.last_done < 25
        ):
            return
        _publish.last_percent = percent
        _publish.last_done = done
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "total": total,
                    "done": done,
                    "success": success_count,
                    "errors": error_count,
                    "percent": percent,
                    "error_details": errors[:10],
                },
            )
        except Exception as e:
            logger.warning(f"Не удалось опубликовать прогресс: {e}")

    _publish.last_percent = -100
    _publish.last_done = 0

    _publish(0, force=True)

    # P-3: весь пакет → processing одним bulk-запросом
    try:
        repo.bulk_update(
            product_ids, {"status": "processing", "error_message": None}, user_id=user_id
        )
    except Exception as e:
        logger.warning(f"Не удалось пометить пакет processing: {e}")

    # P-3: пакетная выборка товаров (selectinload чанками по 100)
    products_by_id = repo.get_by_ids(user_id, product_ids)

    for index, product_id in enumerate(product_ids, 1):
        try:
            product = products_by_id.get(product_id)
            if not product:
                error_count += 1
                errors.append({"id": product_id, "error": "Товар не найден или не принадлежит вам"})
                _publish(index)
                continue

            previous_mapped_category = product.get("mapped_category")
            old_price = _safe_float(product.get("price"))
            old_category = product.get("category")
            source_platform = detect_platform(product.get("source"))

            target_category_name, how = _pick_target_category(
                product, None, target_platform, user_id
            )

            # Дозаполнение пустой логистики и цены по умолчанию из дефолтов.
            # P-3: дефолты не пишутся отдельным запросом на каждый товар, а
            # вливаются в финальный статус-апдейт (см. status_updates ниже)
            upd = defaults_service.build_updates_for_product(product, user_id)
            if upd:
                product.update(upd)
                logger.info(f"🩹 Товар {product_id}: дефолты дописали поля {list(upd)}")

            original_price = _safe_float(product.get("price"))
            price_multiplier = _safe_float(PRICE_RULES.get(target_platform, 1.0), default=1.0)
            final_price = round(original_price * price_multiplier, 2)
            base_source = _base_source(product.get("source"))
            new_source = f"{base_source} → {PLATFORM_CONFIG[target_platform]['name']}"

            if final_price <= 0:
                error_msg = "Цена = 0 ₽ — установите цену через «Обновить цену/бренд» и повторите"
                status_updates.append(
                    (product_id, {**upd, "status": "error", "error_message": error_msg})
                )
                error_count += 1
                errors.append({"id": product_id, "error": error_msg})
                _publish(index)
                continue

            if target_category_name is None:
                error_msg = (
                    "Не найдена точная категория в спеках "
                    f"{target_platform}. Задайте категорию товару (массово: «Обновить цену/бренд» → "
                    "«Категория назначения») или создайте правило в «Маппинг»."
                )
                status_updates.append(
                    (
                        product_id,
                        {
                            **upd,
                            "status": "error",
                            "price": final_price,
                            "mapped_category": previous_mapped_category,
                            "error_message": error_msg,
                        },
                    )
                )
                error_count += 1
                errors.append({"id": product_id, "error": error_msg})
                log_entries.append(
                    {
                        "user_id": user_id,
                        "product_id": product_id,
                        "product_name": product.get("name"),
                        "source_platform": source_platform,
                        "target_platform": target_platform,
                        "old_price": old_price,
                        "new_price": final_price,
                        "old_category": old_category,
                        "new_category": None,
                        "status": "error",
                        "error_message": error_msg,
                        "is_batch": True,
                        "batch_id": self.request.id,
                        "created_at": datetime.utcnow(),
                    }
                )
                logger.warning(f"⚠️ Товар {product_id}: {error_msg}")
            else:
                logger.info(
                    f"📂 Товар {product_id}: категория '{target_category_name}' (источник: {how})"
                )

                _ensure_canonical_attributes(
                    product_id=product_id,
                    target_platform=target_platform,
                    target_category_name=target_category_name,
                    product_name=product.get("name"),
                    okpd_code=product.get("okpd_code"),
                    user_id=user_id,
                )

                status_updates.append(
                    (
                        product_id,
                        {
                            **upd,
                            "status": "success",
                            "source": new_source,
                            "price": final_price,
                            "mapped_category": target_category_name,
                            "error_message": None,
                        },
                    )
                )
                log_entries.append(
                    {
                        "user_id": user_id,
                        "product_id": product_id,
                        "product_name": product.get("name"),
                        "source_platform": source_platform,
                        "target_platform": target_platform,
                        "old_price": old_price,
                        "new_price": final_price,
                        "old_category": old_category,
                        "new_category": target_category_name,
                        "status": "success",
                        "error_message": None,
                        "is_batch": True,
                        "batch_id": self.request.id,
                        "created_at": datetime.utcnow(),
                    }
                )
                success_count += 1
                logger.info(f"✅ Товар {product_id} мигрирован (цена: {old_price} → {final_price})")

        except Exception as e:
            error_count += 1
            errors.append({"id": product_id, "error": str(e)})
            status_updates.append((product_id, {"status": "error", "error_message": str(e)}))
            log_entries.append(
                {
                    "user_id": user_id,
                    "product_id": product_id,
                    "product_name": None,
                    "source_platform": None,
                    "target_platform": target_platform,
                    "old_price": None,
                    "new_price": None,
                    "old_category": None,
                    "new_category": None,
                    "status": "error",
                    "error_message": str(e),
                    "is_batch": True,
                    "batch_id": self.request.id,
                    "created_at": datetime.utcnow(),
                }
            )

        _publish(index)

    # P-3: применяем финальные статусы одним батчем (одна сессия на пакет)
    try:
        repo.update_batch(status_updates, user_id=user_id)
    except Exception as e:
        logger.error(f"Не удалось применить статусы пакета: {e}")

    # P-3: журнал миграций — bulk insert чанками
    for offset in range(0, len(log_entries), 200):
        try:
            op_log.log_migration_batch(log_entries[offset : offset + 200])
        except Exception as e:
            logger.warning(f"Не удалось записать журнал миграций (чанк {offset}): {e}")

    _publish(total, force=True)

    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        f"✅ Пакетная миграция завершена пользователем {user_id}: "
        f"{success_count}/{total} успешно за {duration_ms} мс"
    )
    try:
        stats_repo.record(
            user_id=user_id,
            operation="migrate",
            platform=target_platform,
            status="success" if error_count == 0 else "partial",
            total_items=total,
            success_items=success_count,
            failed_items=error_count,
            duration_ms=duration_ms,
        )
    except Exception as e:
        logger.warning(f"Не удалось записать статистику пакета: {e}")

    return {
        "status": "completed",
        "total": total,
        "success": success_count,
        "errors": error_count,
        "error_details": errors[:10],
        "percent": 100,
        "duration_ms": duration_ms,
    }
