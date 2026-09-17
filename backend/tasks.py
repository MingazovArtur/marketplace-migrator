"""
Celery задачи для фоновой миграции товаров.

Исправления:
  1. Убран дубликат detect_platform — используется единая функция из services.platform_utils
  2. Цена пересчитывается по PRICE_RULES (например, ×1.15 для Wildberries)
  3. mapped_category сохраняется и в одиночной, и в пакетной миграции
  4. Ошибки пишутся в поле error_message товара
  5. Автомаппинг категорий: если категории нет — маппим по названию товара
  6. Все миграции логируются в таблицу migration_logs (Фаза 3)
"""
import logging
import time
from celery_app import celery_app
from services.category_mapper import CategoryMapper
from services.category_service import category_service
from services.platform_utils import detect_platform          # ✅ единая функция
from core.platforms import PLATFORM_CONFIG, PRICE_RULES      # ✅ правила цен
from database.repository import repo, op_log, stats_repo

logger = logging.getLogger(__name__)
category_mapper = CategoryMapper()


def update_progress(task_id, current, total, status="processing",
                    success=0, errors=0, error_details=None):
    """Обновляет прогресс задачи в Redis"""
    try:
        celery_app.backend.store_result(
            task_id,
            {
                "current": current,
                "total": total,
                "percent": round((current / total) * 100, 1) if total > 0 else 0,
                "status": status,
                "success": success,
                "errors": errors,
                "error_details": error_details or [],
            },
            state="PROGRESS",
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить прогресс: {e}")


def get_progress(task_id: str):
    """Получает текущий прогресс задачи по её ID"""
    try:
        result = celery_app.AsyncResult(task_id)
        if result.state == "PROGRESS":
            return result.info
        elif result.state == "SUCCESS":
            task_result = result.result
            if isinstance(task_result, dict) and task_result.get("status") == "success":
                task_result["status"] = "completed"
            return task_result
        elif result.state == "FAILURE":
            return {"status": "error", "message": str(result.result)}
        return {
            "status": "pending",
            "current": 0, "total": 0, "percent": 0,
            "success": 0, "errors": 0, "error_details": [],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _resolve_target_category(category_name: str, product_name: str, target_platform: str):
    """
    Определяет целевую категорию: ручной маппинг не проверяется здесь
    (его делает вызывающий код), здесь — только авто-маппинг.
    ✅ Если категории нет или она 'Не указана' — маппим по названию товара.
    """
    map_text = (
        category_name
        if category_name and category_name != "Не указана"
        else (product_name or "Дом и сад")
    )
    auto_map = category_mapper.auto_map_by_text(map_text, target_platform)
    return auto_map.get("name", "Неизвестно"), map_text


@celery_app.task(bind=True, name="tasks.migrate_product_task")
def migrate_product_task(self, product_id: int, target_platform: str,
                         user_id: int, edited_data: dict = None):
    """
    Фоновая задача для одиночной миграции товара.
    ВАЖНО: проверяет, что товар принадлежит user_id, перед обновлением.
    """
    try:
        product = repo.get_by_id(product_id, user_id=user_id)
        if not product:
            logger.error(f"Товар {product_id} не найден или не принадлежит пользователю {user_id}")
            return {"status": "error", "message": "Товар не найден или не принадлежит вам"}

        repo.update(product_id, {"status": "processing", "error_message": None}, user_id=user_id)

        # --- Запоминаем старые значения для журнала ---
        old_price = product.get("price")
        old_category = product.get("category")
        old_source_platform = detect_platform(product.get("source"))

        source_platform = old_source_platform
        category_name = edited_data.get("category") if edited_data else product.get("category")

        # --- Маппинг категории: ручной приоритетнее авто ---
        mapping = category_service.get_mapping_for_product(
            source_platform, category_name, target_platform, user_id
        )

        if mapping and mapping.get("is_manual"):
            target_category_name = mapping["target_category_name"]
            logger.info(f"Использован ручной маппинг: {category_name} -> {target_category_name}")
        else:
            target_category_name, map_text = _resolve_target_category(
                category_name, product.get("name"), target_platform
            )
            logger.info(f"Использован авто-маппинг: {map_text} -> {target_category_name}")

        # --- ✅ Пересчёт цены по PRICE_RULES ---
        original_price = edited_data.get("price") if edited_data else (product.get("price") or 0)
        price_multiplier = PRICE_RULES.get(target_platform, 1.0)
        final_price = round(original_price * price_multiplier, 2)

        # Заглушка для имитации работы с API (в prod убрать)
        time.sleep(1)

        final_name = edited_data.get("name") if edited_data else product.get("name")
        new_source = f"{product['source']} → {PLATFORM_CONFIG[target_platform]['name']}"

        repo.update(product_id, {
            "status": "success",
            "source": new_source,
            "name": final_name,
            "price": final_price,
            "category": category_name,
            "mapped_category": target_category_name,
            "error_message": None,
        }, user_id=user_id)

        t0 = time.perf_counter()
        stats_repo.record(
            user_id=user_id, operation="migrate", platform=target_platform,
            status="success", total_items=1, success_items=1,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

        # --- ✅ Журнал миграции ---
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
            f"✅ Товар {product_id} успешно мигрирован пользователем {user_id} "
            f"(цена: {old_price} → {final_price})"
        )
        return {"status": "completed", "product_id": product_id}

    except Exception as e:
        logger.error(f"❌ Ошибка миграции товара {product_id}: {e}")
        repo.update(product_id, {"status": "error", "error_message": str(e)}, user_id=user_id)
        stats_repo.record(user_id=user_id, operation="migrate",
            platform=target_platform, status="error", total_items=1,
            failed_items=1,
            duration_ms=int((time.perf_counter() - t0) * 1000))
        # --- ✅ Журнал ошибки миграции ---
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


@celery_app.task(bind=True, name="tasks.migrate_batch_task")
def migrate_batch_task(self, product_ids: list, target_platform: str, user_id: int):
    """Пакетная миграция товаров с отслеживанием прогресса и журналом"""
    total = len(product_ids)
    success_count = 0
    error_count = 0
    errors = []

    for index, product_id in enumerate(product_ids, 1):
        try:
            product = repo.get_by_id(product_id, user_id=user_id)
            if not product:
                error_count += 1
                errors.append({"id": product_id, "error": "Товар не найден или не принадлежит вам"})

                # --- ✅ Журнал: товар не найден ---
                op_log.log_migration(
                    user_id=user_id, product_id=product_id, product_name=None,
                    source_platform=None, target_platform=target_platform,
                    status="error", error_message="Товар не найден или не принадлежит вам",
                    is_batch=True, batch_id=self.request.id,
                )
                update_progress(self.request.id, index, total, "processing",
                                success_count, error_count, errors)
                continue

            # --- Запоминаем старые значения ---
            old_price = product.get("price")
            old_category = product.get("category")
            source_platform = detect_platform(product.get("source"))
            category_name = product.get("category")

            # --- Маппинг категории ---
            mapping = category_service.get_mapping_for_product(
                source_platform, category_name, target_platform, user_id
            )

            if mapping and mapping.get("is_manual"):
                target_category_name = mapping["target_category_name"]
            else:
                target_category_name, map_text = _resolve_target_category(
                    category_name, product.get("name"), target_platform
                )

            # --- ✅ Пересчёт цены по PRICE_RULES ---
            original_price = product.get("price") or 0
            price_multiplier = PRICE_RULES.get(target_platform, 1.0)
            final_price = round(original_price * price_multiplier, 2)

            # Заглушка для имитации работы с API (в prod убрать)
            time.sleep(1)

            new_source = f"{product['source']} → {PLATFORM_CONFIG[target_platform]['name']}"
            repo.update(product_id, {
                "status": "success",
                "source": new_source,
                "price": final_price,               # ✅ обновляем цену
                "mapped_category": target_category_name,  # ✅ сохраняем категорию
                "error_message": None,
            }, user_id=user_id)

            # --- ✅ Журнал успешной миграции ---
            op_log.log_migration(
                user_id=user_id,
                product_id=product_id,
                product_name=product.get("name"),
                source_platform=source_platform,
                target_platform=target_platform,
                old_price=old_price,
                new_price=final_price,
                old_category=old_category,
                new_category=target_category_name,
                status="success",
                error_message=None,
                is_batch=True,
                batch_id=self.request.id,
            )

            success_count += 1
            logger.info(f"✅ Товар {product_id} мигрирован (цена: {old_price} → {final_price})")

        except Exception as e:
            error_count += 1
            errors.append({"id": product_id, "error": str(e)})
            repo.update(product_id, {"status": "error", "error_message": str(e)}, user_id=user_id)

            # --- ✅ Журнал ошибки миграции ---
            op_log.log_migration(
                user_id=user_id,
                product_id=product_id,
                product_name=None,
                source_platform=None,
                target_platform=target_platform,
                status="error",
                error_message=str(e),
                is_batch=True,
                batch_id=self.request.id,
            )

        update_progress(self.request.id, index, total, "processing",
                        success_count, error_count, errors)

    result = {
        "status": "completed",
        "total": total,
        "success": success_count,
        "errors": error_count,
        "error_details": errors[:10],
        "percent": 100,
    }
    celery_app.backend.store_result(self.request.id, result, state="SUCCESS")
    logger.info(
        f"✅ Пакетная миграция завершена пользователем {user_id}: "
        f"{success_count}/{total} успешно"
    )
    stats_repo.record(
        user_id=user_id, operation="migrate", platform=target_platform,
        status="success" if error_count == 0 else "partial",
        total_items=total, success_items=success_count, failed_items=error_count,
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
    return result

@celery_app.task(bind=True, name="tasks.download_photos_task")
def download_photos_task(self, product_id: int, user_id: int):
    """Фоновое скачивание копий фото товара"""
    from services.media_service import download_photos

    product = repo.get_by_id(product_id, user_id=user_id)
    if not product:
        return {"status": "error", "message": "Товар не найден"}

    urls = product.get("photos") or []
    if not urls:
        return {"status": "error", "message": "У товара нет фото"}

    saved = download_photos(product_id, urls)

    op_log.log_file_operation(
        user_id=user_id,
        operation="media_download",
        platform=None,
        filename=f"товар #{product_id}",
        status="success" if saved else "error",
        total_rows=len(urls),
        imported=len(saved),
        failed=len(urls) - len(saved),
    )

    logger.info(f"💾 Товар {product_id}: скачано {len(saved)} из {len(urls)} фото")
    return {"status": "completed", "saved": len(saved), "total": len(urls)}