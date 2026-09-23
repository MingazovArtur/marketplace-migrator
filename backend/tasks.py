"""
Celery задачи для фоновой миграции товаров и загрузки спеков площадок.

Исправления:
  1. Убран дубликат detect_platform — используется единая функция из services.platform_utils
  2. Цена пересчитывается по PRICE_RULES (например, ×1.15 для Wildberries)
  3. mapped_category сохраняется и в одиночной, и в пакетной миграции
  4. Ошибки пишутся в поле error_message товара
  5. Автомаппинг категорий: если категории нет — маппим по названию товара
  6. Все миграции логируются в таблицу migration_logs (Фаза 3)
  7. ✅ Прогресс публикуется через self.update_state (работает с AsyncResult.info)
  8. ✅ Унифицированные имена полей: status ∈ {pending, progress, completed, failed}, done
  9. ✅ t0 в самом начале задач — защита от NameError в except
 10. ✅ Убрана искусственная задержка time.sleep(1) в пакетной миграции
 11. ✅ Задача refresh_specs_task — фоновая загрузка спеков площадок с прогрессом
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


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def get_progress(task_id: str) -> dict:
    """
    Возвращает текущий прогресс задачи по её ID в унифицированном формате:
        status: 'pending' | 'progress' | 'completed' | 'failed'
        + поля total, done, success, errors, percent, error (опц.)

    Работает одинаково для задач миграции И задач загрузки спеков.
    """
    try:
        result = celery_app.AsyncResult(task_id)

        if result.state == "PROGRESS":
            meta = result.info or {}
            total = meta.get("total", 0)
            done = meta.get("done", 0)
            return {
                "status": "progress",
                "total": total,
                "done": done,
                "success": meta.get("success", 0),
                "errors": meta.get("errors", 0),
                "percent": meta.get("percent", int(done * 100 / total) if total else 0),
                "error_details": meta.get("error_details", []),
            }

        if result.state == "SUCCESS":
            r = result.result or {}
            if isinstance(r, dict):
                # ✅ Поддержка обоих форматов: миграций (success) и спеков (fetched)
                total = r.get("total") or r.get("fetched", 0) + r.get("errors", 0)
                success = r.get("success") or r.get("fetched", 0)
                errors = r.get("errors", 0)
                return {
                    "status": "completed",
                    "total": total,
                    "done": total,
                    "success": success,
                    "errors": errors,
                    "percent": 100,
                    "error_details": r.get("error_details", []),
                    "platform": r.get("platform"),
                }
            return {"status": "completed", "total": 0, "done": 0, "success": 0, "errors": 0, "percent": 100}

        if result.state == "FAILURE":
            return {
                "status": "failed",
                "total": 0, "done": 0, "success": 0, "errors": 0, "percent": 0,
                "error": str(result.info) if result.info else "Неизвестная ошибка",
            }

        # PENDING / STARTED / RECEIVED
        return {
            "status": "pending",
            "total": 0, "done": 0, "success": 0, "errors": 0, "percent": 0,
        }

    except Exception as e:
        logger.warning(f"Не удалось получить прогресс задачи {task_id}: {e}")
        return {
            "status": "failed",
            "total": 0, "done": 0, "success": 0, "errors": 0, "percent": 0,
            "error": str(e),
        }


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


# ---------------------------------------------------------------------------
# Одиночная миграция
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="tasks.migrate_product_task")
def migrate_product_task(self, product_id: int, target_platform: str,
                         user_id: int, edited_data: dict = None):
    """
    Фоновая задача для одиночной миграции товара.
    ВАЖНО: проверяет, что товар принадлежит user_id, перед обновлением.
    """
    t0 = time.perf_counter()                 # ✅ t0 в самом начале
    final_price = None                       # ✅ защита от NameError в except

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

        # Небольшая задержка, чтобы было видно статус "processing" в UI
        time.sleep(0.3)

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

        duration_ms = int((time.perf_counter() - t0) * 1000)

        stats_repo.record(
            user_id=user_id, operation="migrate", platform=target_platform,
            status="success", total_items=1, success_items=1,
            duration_ms=duration_ms,
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
        duration_ms = int((time.perf_counter() - t0) * 1000)
        try:
            repo.update(product_id, {"status": "error", "error_message": str(e)}, user_id=user_id)
        except Exception:
            pass
        try:
            stats_repo.record(
                user_id=user_id, operation="migrate", platform=target_platform,
                status="error", total_items=1, failed_items=1,
                duration_ms=duration_ms,
            )
        except Exception:
            pass
        # --- ✅ Журнал ошибки миграции ---
        try:
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
        except Exception:
            pass
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Пакетная миграция
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="tasks.migrate_batch_task")
def migrate_batch_task(self, product_ids: list, target_platform: str, user_id: int):
    """Пакетная миграция товаров с отслеживанием прогресса и журналом"""
    t0 = time.perf_counter()                 # ✅ t0 в самом начале
    total = len(product_ids)
    success_count = 0
    error_count = 0
    errors = []

    # Сразу публикуем "старт": 0%
    self.update_state(
        state="PROGRESS",
        meta={
            "total": total, "done": 0, "success": 0, "errors": 0,
            "percent": 0, "error_details": [],
        },
    )

    for index, product_id in enumerate(product_ids, 1):
        try:
            product = repo.get_by_id(product_id, user_id=user_id)
            if not product:
                error_count += 1
                errors.append({"id": product_id, "error": "Товар не найден или не принадлежит вам"})
                try:
                    op_log.log_migration(
                        user_id=user_id, product_id=product_id, product_name=None,
                        source_platform=None, target_platform=target_platform,
                        status="error", error_message="Товар не найден или не принадлежит вам",
                        is_batch=True, batch_id=self.request.id,
                    )
                except Exception:
                    pass
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "total": total, "done": index,
                        "success": success_count, "errors": error_count,
                        "percent": int(index * 100 / total) if total else 0,
                        "error_details": errors[:10],
                    },
                )
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
                target_category_name, _ = _resolve_target_category(
                    category_name, product.get("name"), target_platform
                )

            # --- ✅ Пересчёт цены по PRICE_RULES ---
            original_price = product.get("price") or 0
            price_multiplier = PRICE_RULES.get(target_platform, 1.0)
            final_price = round(original_price * price_multiplier, 2)

            new_source = f"{product['source']} → {PLATFORM_CONFIG[target_platform]['name']}"
            repo.update(product_id, {
                "status": "success",
                "source": new_source,
                "price": final_price,
                "mapped_category": target_category_name,
                "error_message": None,
            }, user_id=user_id)

            # --- ✅ Журнал успешной миграции ---
            try:
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
            except Exception:
                pass

            success_count += 1
            logger.info(f"✅ Товар {product_id} мигрирован (цена: {old_price} → {final_price})")

        except Exception as e:
            error_count += 1
            errors.append({"id": product_id, "error": str(e)})
            try:
                repo.update(product_id, {"status": "error", "error_message": str(e)}, user_id=user_id)
            except Exception:
                pass
            try:
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
            except Exception:
                pass

        # ✅ ПУБЛИКАЦИЯ ПРОГРЕССА после каждой итерации через self.update_state
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "total": total,
                    "done": index,
                    "success": success_count,
                    "errors": error_count,
                    "percent": int(index * 100 / total) if total else 0,
                    "error_details": errors[:10],
                },
            )
        except Exception as e:
            logger.warning(f"Не удалось опубликовать прогресс: {e}")

    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        f"✅ Пакетная миграция завершена пользователем {user_id}: "
        f"{success_count}/{total} успешно за {duration_ms} мс"
    )

    try:
        stats_repo.record(
            user_id=user_id, operation="migrate", platform=target_platform,
            status="success" if error_count == 0 else "partial",
            total_items=total, success_items=success_count, failed_items=error_count,
            duration_ms=duration_ms,
        )
    except Exception as e:
        logger.warning(f"Не удалось записать статистику пакета: {e}")

    # ✅ Возвращаем финальный результат — Celery сам сохранит его в SUCCESS
    return {
        "status": "completed",
        "total": total,
        "success": success_count,
        "errors": error_count,
        "error_details": errors[:10],
        "percent": 100,
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Скачивание фото
# ---------------------------------------------------------------------------

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

    try:
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
    except Exception as e:
        logger.warning(f"Не удалось записать лог скачивания фото: {e}")

    logger.info(f"💾 Товар {product_id}: скачано {len(saved)} из {len(urls)} фото")
    return {"status": "completed", "saved": len(saved), "total": len(urls)}


# ---------------------------------------------------------------------------
# ✅ НОВОЕ: Фоновая загрузка спеков площадок
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="tasks.refresh_specs_task")
def refresh_specs_task(self, user_id: int, platform: str, raw_api_key: str, category_ids=None):
    """
    Фоновая загрузка спеков категорий площадки через её API.
    
    Аргументы:
        user_id: ID пользователя
        platform: 'ozon' | 'yandex' | 'wildberries'
        raw_api_key: строка формата 'CLIENT_ID:API_KEY' (для Ozon)
        category_ids: опциональный список ID категорий (для частичной загрузки)
    
    Прогресс публикуется через self.update_state — UI получает live-обновления.
    Использует тот же формат (status/done/success/errors/percent) что и миграции,
    чтобы `get_progress` работал без изменений.
    """
    import asyncio
    # Ленивый импорт — защита от circular import при старте Celery
    from services.ozon_specs import refresh_ozon_specs

    t0 = time.perf_counter()
    logger.info(f"🚀 Старт загрузки спеков {platform} для пользователя {user_id}")

    # ✅ Колбэк прогресса — передаётся в refresh_ozon_specs
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
        # elif platform == "yandex":
        #     from services.yandex_specs import refresh_yandex_specs
        #     result = asyncio.run(refresh_yandex_specs(...))
        # elif platform == "wildberries":
        #     from services.wb_specs import refresh_wildberries_specs
        #     result = asyncio.run(refresh_wildberries_specs(...))
        else:
            raise ValueError(f"Загрузчик спеков для {platform} ещё не реализован")

        fetched = result.get("fetched", 0)
        errors = result.get("errors", 0)
        total = fetched + errors
        duration_ms = int((time.perf_counter() - t0) * 1000)

        logger.info(
            f"✅ Спеки {platform} загружены: {fetched} категорий, {errors} ошибок за {duration_ms} мс"
        )

        # --- Статистика ---
        try:
            stats_repo.record(
                user_id=user_id, operation="specs_refresh", platform=platform,
                status="success" if errors == 0 else "partial",
                total_items=total, success_items=fetched, failed_items=errors,
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

        try:
            stats_repo.record(
                user_id=user_id, operation="specs_refresh", platform=platform,
                status="error", total_items=0, failed_items=1,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

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