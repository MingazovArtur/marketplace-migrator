"""
Celery задачи для фоновой миграции товаров и загрузки спеков площадок.
"""
import logging
import time

from celery_app import celery_app
from services.category_mapper import CategoryMapper
from services.category_service import category_service
from services.platform_utils import detect_platform
from core.platforms import PLATFORM_CONFIG, PRICE_RULES
from database.repository import repo, op_log, stats_repo

logger = logging.getLogger(__name__)
category_mapper = CategoryMapper()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _safe_float(value, default: float = 0.0) -> float:
    """Безопасное преобразование в float (строки, Decimal, None → default)."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(f"⚠️ Не удалось преобразовать '{value}' в float → {default}")
        return default


def _base_source(source_value: str) -> str:
    """
    Базовый источник импорта — часть до первой стрелки « → ».
    Защита от накопления «Магнит Маркет (Файл) → Ozon → Ozon → Ozon»
    при повторных миграциях одного и того же товара.
    """
    if not source_value:
        return "неизвестно"
    return str(source_value).split(" → ")[0].strip()


def _spec_name_exists(platform: str, name) -> bool:
    """Существует ли ТОЧНОЕ имя категории в спеках площадки."""
    if not name:
        return False
    from database.session import SessionLocal
    from database.models import PlatformCategorySpec
    db = SessionLocal()
    try:
        return db.query(PlatformCategorySpec.id).filter(
            PlatformCategorySpec.platform == platform,
            PlatformCategorySpec.category_name == str(name).strip(),
        ).first() is not None
    finally:
        db.close()


def _match_spec_by_text(text, platform: str):
    """
    Умный поиск спека по тексту товара/категории.
    Ищет ТОЧНОЕ имя из platform_category_specs, где:
      1) ТИП (часть после '/') полностью входит в текст — самый высокий приоритет (score ≥ 100);
      2) ТИП начинается с введённой подстроки (≥4 символов) — префикс-матчинг (score ≥ 50).
    Берёт самый длинный совпавший тип (более специфичный).
    """
    if not text:
        return None
    from database.session import SessionLocal
    from database.models import PlatformCategorySpec
    low = str(text).lower().strip()
    if not low:
        return None
    db = SessionLocal()
    try:
        names = [n for (n,) in db.query(PlatformCategorySpec.category_name)
                 .filter(PlatformCategorySpec.platform == platform).all()]
    finally:
        db.close()

    best, best_score = None, 0
    for name in names:
        type_part = name.lower().split("/")[-1].strip()
        if not type_part or len(type_part) < 4:
            continue
        score = 0
        if type_part in low:
            score = 100 + len(type_part)
        elif len(low) >= 4 and type_part.startswith(low):
            score = 50 + len(type_part)
        if score > best_score:
            best, best_score = name, score
    return best


def _pick_target_category(product: dict, edited_category, target_platform: str, user_id: int):
    """
    Единая точка определения целевой категории. Возвращает (имя_спека, источник).

    Приоритеты:
      1) категория из модалки миграции — если это ТОЧНОЕ имя спека;
      2) уже выставленный product.mapped_category — если он валиден;
      3) ручное правило из раздела «Маппинг»;
      4) авто-маппинг по тексту + проверка по спекам;
      5) поиск типа товара по спекам (с префикс-матчингом);
      6) None → миграция завершится ошибкой с инструкцией.
    """
    # 1) Категория из модалки
    if edited_category and _spec_name_exists(target_platform, edited_category):
        return str(edited_category).strip(), "модалка"

    # 2) Уже выставленный mapped_category
    existing = product.get("mapped_category")
    if existing and _spec_name_exists(target_platform, existing):
        return existing, "mapped_category"

    # 3) Ручной маппинг
    source_platform = detect_platform(product.get("source"))
    mapping = category_service.get_mapping_for_product(
        source_platform, product.get("category"), target_platform, user_id
    )
    if mapping and mapping.get("is_manual"):
        name = mapping.get("target_category_name")
        if _spec_name_exists(target_platform, name):
            return name, "ручной маппинг"
        logger.warning(f"⚠️ Ручной маппинг указывает на '{name}', но её нет в спеках — игнорирую")

    # 4) Авто-маппинг + проверка
    category_name = product.get("category")
    map_text = (
        category_name if category_name and category_name != "Не указана"
        else (product.get("name") or "Дом и сад")
    )
    auto_map = category_mapper.auto_map_by_text(map_text, target_platform)
    auto_name = auto_map.get("name") if auto_map else None
    if auto_name and auto_name != "Неизвестно":
        if _spec_name_exists(target_platform, auto_name):
            return auto_name, "авто-маппинг"
        logger.warning(
            f"⚠️ Авто-маппинг нашёл '{auto_name}', но такой категории нет в спеках {target_platform}"
        )

    # 5) Поиск типа товара по спекам
    spec_name = (_match_spec_by_text(map_text, target_platform)
                 or _match_spec_by_text(product.get("name"), target_platform))
    if spec_name:
        return spec_name, "поиск по спекам"

    return None, "не найдено"


def get_progress(task_id: str) -> dict:
    """
    Текущий прогресс задачи по ID: status ∈ pending|progress|completed|failed
    + total, done, success, errors, percent, error_details.
    """
    try:
        result = celery_app.AsyncResult(task_id)

        if result.state == "PROGRESS":
            meta = result.info or {}
            total = meta.get("total", 0)
            done = meta.get("done", 0)
            return {
                "status": "progress",
                "total": total, "done": done,
                "success": meta.get("success", 0),
                "errors": meta.get("errors", 0),
                "percent": meta.get("percent", int(done * 100 / total) if total else 0),
                "error_details": meta.get("error_details", []),
            }

        if result.state == "SUCCESS":
            r = result.result or {}
            if isinstance(r, dict):
                total = r.get("total") or (r.get("fetched", 0) + r.get("errors", 0))
                success = r.get("success") or r.get("fetched", 0)
                errors = r.get("errors", 0)
                return {
                    "status": "completed",
                    "total": total, "done": total,
                    "success": success, "errors": errors, "percent": 100,
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

        return {"status": "pending", "total": 0, "done": 0, "success": 0, "errors": 0, "percent": 0}

    except Exception as e:
        logger.warning(f"Не удалось получить прогресс задачи {task_id}: {e}")
        return {
            "status": "failed",
            "total": 0, "done": 0, "success": 0, "errors": 0, "percent": 0, "error": str(e),
        }


# ---------------------------------------------------------------------------
# Одиночная миграция
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="tasks.migrate_product_task")
def migrate_product_task(self, product_id: int, target_platform: str,
                         user_id: int, edited_data: dict = None):
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

        repo.update(product_id, {"status": "processing", "error_message": None}, user_id=user_id)

        old_price = _safe_float(product.get("price"))
        old_category = product.get("category")
        source_platform = detect_platform(product.get("source"))

        edited_category = edited_data.get("category") if edited_data else None
        target_category_name, how = _pick_target_category(
            product, edited_category, target_platform, user_id
        )
        if target_category_name:
            logger.info(f"📂 Товар {product_id}: категория '{target_category_name}' (источник: {how})")

        original_price = _safe_float(
            edited_data.get("price") if edited_data else product.get("price")
        )
        price_multiplier = _safe_float(PRICE_RULES.get(target_platform, 1.0), default=1.0)
        final_price = round(original_price * price_multiplier, 2)

        time.sleep(0.3)

        final_name = edited_data.get("name") if edited_data else product.get("name")
        base_source = _base_source(product.get("source"))
        new_source = f"{base_source} → {PLATFORM_CONFIG[target_platform]['name']}"

        if target_category_name is None:
            error_msg = (
                f"Не найдена точная категория в спеках {target_platform} для товара '{final_name}'. "
                f"Выберите категорию в модалке миграции из выпадающего списка "
                f"(формат «Родитель / Тип», например «Одежда / Футболка») "
                f"или задайте её в разделе «Маппинг». Список имён — на странице «Спецификации»."
            )
            repo.update(product_id, {
                "status": "error",
                "name": final_name,
                "price": final_price,
                "mapped_category": None,
                "error_message": error_msg,
            }, user_id=user_id)
            logger.warning(f"⚠️ Товар {product_id}: {error_msg}")
            return {"status": "error", "message": error_msg, "product_id": product_id}

        repo.update(product_id, {
            "status": "success",
            "source": new_source,
            "name": final_name,
            "price": final_price,
            "mapped_category": target_category_name,
            "error_message": None,
        }, user_id=user_id)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        stats_repo.record(
            user_id=user_id, operation="migrate", platform=target_platform,
            status="success", total_items=1, success_items=1, duration_ms=duration_ms,
        )
        op_log.log_migration(
            user_id=user_id, product_id=product_id, product_name=final_name,
            source_platform=source_platform, target_platform=target_platform,
            old_price=old_price, new_price=final_price,
            old_category=old_category, new_category=target_category_name,
            status="success", error_message=None, is_batch=False, batch_id=self.request.id,
        )
        logger.info(
            f"✅ Товар {product_id} мигрирован (цена: {old_price} → {final_price}, "
            f"категория: {target_category_name})"
        )
        return {"status": "completed", "product_id": product_id}

    except Exception as e:
        logger.error(f"❌ Ошибка миграции товара {product_id}: {e}", exc_info=True)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        try:
            repo.update(product_id, {"status": "error", "error_message": str(e)}, user_id=user_id)
        except Exception:
            pass
        try:
            stats_repo.record(
                user_id=user_id, operation="migrate", platform=target_platform,
                status="error", total_items=1, failed_items=1, duration_ms=duration_ms,
            )
        except Exception:
            pass
        try:
            op_log.log_migration(
                user_id=user_id, product_id=product_id, product_name=None,
                source_platform=None, target_platform=target_platform,
                status="error", error_message=str(e), is_batch=False, batch_id=self.request.id,
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
    t0 = time.perf_counter()
    total = len(product_ids)
    success_count = 0
    error_count = 0
    errors = []

    self.update_state(state="PROGRESS", meta={
        "total": total, "done": 0, "success": 0, "errors": 0, "percent": 0, "error_details": [],
    })

    for index, product_id in enumerate(product_ids, 1):
        try:
            product = repo.get_by_id(product_id, user_id=user_id)
            if not product:
                error_count += 1
                errors.append({"id": product_id, "error": "Товар не найден или не принадлежит вам"})
                self.update_state(state="PROGRESS", meta={
                    "total": total, "done": index, "success": success_count,
                    "errors": error_count,
                    "percent": int(index * 100 / total) if total else 0,
                    "error_details": errors[:10],
                })
                continue

            old_price = _safe_float(product.get("price"))
            old_category = product.get("category")
            source_platform = detect_platform(product.get("source"))

            target_category_name, how = _pick_target_category(
                product, None, target_platform, user_id
            )

            original_price = _safe_float(product.get("price"))
            price_multiplier = _safe_float(PRICE_RULES.get(target_platform, 1.0), default=1.0)
            final_price = round(original_price * price_multiplier, 2)
            base_source = _base_source(product.get("source"))
            new_source = f"{base_source} → {PLATFORM_CONFIG[target_platform]['name']}"

            if target_category_name is None:
                error_msg = (
                    "Не найдена точная категория в спеках "
                    f"{target_platform}. Задайте категорию товару (массово: «Обновить цену/бренд» → "
                    "«Категория назначения») или создайте правило в «Маппинг»."
                )
                repo.update(product_id, {
                    "status": "error",
                    "price": final_price,
                    "mapped_category": None,
                    "error_message": error_msg,
                }, user_id=user_id)
                error_count += 1
                errors.append({"id": product_id, "error": error_msg})
                try:
                    op_log.log_migration(
                        user_id=user_id, product_id=product_id,
                        product_name=product.get("name"),
                        source_platform=source_platform, target_platform=target_platform,
                        old_price=old_price, new_price=final_price,
                        old_category=old_category, new_category=None,
                        status="error", error_message=error_msg,
                        is_batch=True, batch_id=self.request.id,
                    )
                except Exception:
                    pass
                logger.warning(f"⚠️ Товар {product_id}: {error_msg}")
            else:
                logger.info(f"📂 Товар {product_id}: категория '{target_category_name}' (источник: {how})")
                repo.update(product_id, {
                    "status": "success",
                    "source": new_source,
                    "price": final_price,
                    "mapped_category": target_category_name,
                    "error_message": None,
                }, user_id=user_id)
                try:
                    op_log.log_migration(
                        user_id=user_id, product_id=product_id,
                        product_name=product.get("name"),
                        source_platform=source_platform, target_platform=target_platform,
                        old_price=old_price, new_price=final_price,
                        old_category=old_category, new_category=target_category_name,
                        status="success", error_message=None,
                        is_batch=True, batch_id=self.request.id,
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
                    user_id=user_id, product_id=product_id, product_name=None,
                    source_platform=None, target_platform=target_platform,
                    status="error", error_message=str(e), is_batch=True, batch_id=self.request.id,
                )
            except Exception:
                pass

        try:
            self.update_state(state="PROGRESS", meta={
                "total": total, "done": index,
                "success": success_count, "errors": error_count,
                "percent": int(index * 100 / total) if total else 0,
                "error_details": errors[:10],
            })
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

    return {
        "status": "completed", "total": total,
        "success": success_count, "errors": error_count,
        "error_details": errors[:10], "percent": 100, "duration_ms": duration_ms,
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
            user_id=user_id, operation="media_download", platform=None,
            filename=f"товар #{product_id}",
            status="success" if saved else "error",
            total_rows=len(urls), imported=len(saved), failed=len(urls) - len(saved),
        )
    except Exception as e:
        logger.warning(f"Не удалось записать лог скачивания фото: {e}")

    logger.info(f"💾 Товар {product_id}: скачано {len(saved)} из {len(urls)} фото")
    return {"status": "completed", "saved": len(saved), "total": len(urls)}


# ---------------------------------------------------------------------------
# Фоновая загрузка спеков площадок
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="tasks.refresh_specs_task")
def refresh_specs_task(self, user_id: int, platform: str, raw_api_key: str, category_ids=None):
    """Фоновая загрузка спеков категорий площадки через её API."""
    import asyncio
    from services.ozon_specs import refresh_ozon_specs

    t0 = time.perf_counter()
    logger.info(f"🚀 Старт загрузки спеков {platform} для пользователя {user_id}")

    def progress_cb(p: dict):
        try:
            total = p.get("total", 0)
            fetched = p.get("fetched", 0)
            errors = p.get("errors", 0)
            done = fetched + errors
            percent = int(done * 100 / total) if total else 0
            self.update_state(state="PROGRESS", meta={
                "total": total, "done": done, "success": fetched, "errors": errors,
                "percent": percent, "platform": platform, "error_details": [],
            })
        except Exception as e:
            logger.warning(f"Не удалось опубликовать прогресс спеков: {e}")

    try:
        if platform == "ozon":
            result = asyncio.run(refresh_ozon_specs(
                user_id=user_id, raw_api_key=raw_api_key,
                category_ids=category_ids, progress_cb=progress_cb,
            ))
        else:
            raise ValueError(f"Загрузчик спеков для {platform} ещё не реализован")

        fetched = result.get("fetched", 0)
        errors = result.get("errors", 0)
        total = fetched + errors
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"✅ Спеки {platform} загружены: {fetched} категорий, {errors} ошибок за {duration_ms} мс")

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
            "status": "completed", "platform": platform, "total": total, "done": total,
            "success": fetched, "fetched": fetched, "errors": errors, "percent": 100,
            "error_details": result.get("error_details", []), "duration_ms": duration_ms,
        }

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки спеков {platform}: {e}", exc_info=True)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        try:
            stats_repo.record(
                user_id=user_id, operation="specs_refresh", platform=platform,
                status="error", total_items=0, failed_items=1, duration_ms=duration_ms,
            )
        except Exception:
            pass
        return {
            "status": "error", "platform": platform, "total": 0, "done": 0,
            "success": 0, "errors": 1, "percent": 0,
            "message": str(e), "error_details": [{"error": str(e)}],
        }