"""Оркестратор загрузки спеков Ozon: дерево → атрибуты → чанковая запись в БД.

Вызывается из tasks.refresh_specs_task (tasks/catalog_tasks.py). Вынесено без
изменений из монолита services/ozon_specs.py (Р8): зависимости (дерево, сборка
спека, запись в БД, HTTP-политика) импортированы сюда — тело функции не менялось.
"""

import asyncio
import gc
import logging
from collections.abc import Callable

import httpx

from services.ozon_specs._attributes import _build_spec
from services.ozon_specs._http import CONCURRENCY, TIMEOUT, _ozon_headers, _parse_ozon_key
from services.ozon_specs._storage import DB_CHUNK, _flush_buffer
from services.ozon_specs._tree import fetch_ozon_category_tree

logger = logging.getLogger(__name__)

PROGRESS_EVERY = 10  # частота вызова progress_cb (чаще для мониторинга)


async def refresh_ozon_specs(
    user_id: int,
    raw_api_key: str,
    category_ids: list[str] | None = None,
    progress_cb: Callable | None = None,
    concurrency: int = CONCURRENCY,
    skip_category_ids: list[str] | None = None,
    pause_check: Callable[[], bool] | None = None,
    done_keys: set | None = None,
) -> dict:
    """
    Фоновая загрузка спеков Ozon с оптимизацией памяти.
    Возвращает {"platform", "fetched", "errors", "error_details"};
    при остановке админом — {"paused": True, ...}.

    skip_category_ids — ключи категорий вида "{id}_{type_id}", которые уже
    сохранены в БД (продолжение после паузы) — их пропускаем.
    pause_check — колбэк «админ просил паузу», проверяется между блоками.
    done_keys — сюда складываются ключи успешно сохранённых категорий
    (передаётся из refresh_specs_task и пишется в реестр при паузе).
    """
    client_id, api_key = _parse_ozon_key(raw_api_key)
    headers = _ozon_headers(client_id, api_key)

    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(
        max_connections=concurrency + 5,
        max_keepalive_connections=concurrency,
    )

    fetched = 0
    errors = 0
    error_details = []
    done_count = 0
    buffer: list[tuple[dict, dict]] = []

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits) as client:
        # 1) Дерево категорий
        leaves = await fetch_ozon_category_tree(client, sem, client_id, api_key)
        leaves = [n for n in leaves if n.get("id") and n.get("type_id")]

        if category_ids:
            wanted = {str(c) for c in category_ids}
            leaves = [n for n in leaves if n["id"] in wanted]

        # Продолжение после паузы: пропускаем уже сохранённые категории
        if skip_category_ids:
            skip = {str(c) for c in skip_category_ids}
            before = len(leaves)
            leaves = [n for n in leaves if f"{n['id']}_{n['type_id']}" not in skip]
            if before != len(leaves):
                logger.info(f"⏩ Ozon: пропущено {before - len(leaves)} категорий из прошлой загрузки")

        total = len(leaves)
        logger.info(f"🚀 Ozon: будет загружено {total} категорий (concurrency={concurrency})")

        if progress_cb:
            progress_cb({"total": total, "fetched": 0, "errors": 0})

        if total == 0:
            return {
                "platform": "ozon",
                "fetched": 0,
                "errors": 0,
                "error_details": [],
            }

        # 2) Обработка чанками: параллельно внутри, commit между чанками
        async def work(leaf: dict) -> None:
            nonlocal fetched, errors, done_count
            try:
                spec = await _build_spec(client, sem, headers, leaf)
                buffer.append((leaf, spec))
                fetched += 1
            except Exception as e:
                errors += 1
                if len(error_details) < 50:
                    error_details.append(
                        {
                            "category_id": leaf.get("id"),
                            "type_id": leaf.get("type_id"),
                            "error": str(e)[:300],
                        }
                    )
            finally:
                done_count += 1
                if progress_cb and (done_count % PROGRESS_EVERY == 0 or done_count == total):
                    progress_cb({"total": total, "fetched": fetched, "errors": errors})

        for i in range(0, total, DB_CHUNK):
            # Кооперативная пауза: проверяем флаг между блоками категорий.
            # Текущий блок дообрабатывается и коммитится, прогресс не теряется.
            if pause_check and pause_check():
                logger.info(f"⏸ Ozon: пауза на {done_count}/{total} — блоки до сюда сохранены")
                return {
                    "platform": "ozon",
                    "paused": True,
                    "fetched": fetched,
                    "errors": errors,
                    "error_details": error_details,
                }

            chunk = leaves[i : i + DB_CHUNK]
            await asyncio.gather(*(work(leaf) for leaf in chunk))

            # Commit чанка в БД
            flushed = list(buffer)
            try:
                _flush_buffer(user_id, buffer)
                if done_keys is not None:
                    done_keys.update(f"{leaf['id']}_{leaf['type_id']}" for leaf, _ in flushed)
            except Exception as e:
                logger.error(f"❌ Ошибка commit чанка {i // DB_CHUNK}: {e}")
                errors += len(buffer)
                for leaf, _ in buffer:
                    if len(error_details) < 50:
                        error_details.append(
                            {
                                "category_id": leaf.get("id"),
                                "type_id": leaf.get("type_id"),
                                "error": f"DB commit failed: {e}",
                            }
                        )

            # ✅ ОЧИСТКА ПАМЯТИ после каждого чанка
            buffer.clear()
            gc.collect()

            logger.info(
                f"📦 Прогресс Ozon: {done_count}/{total} " f"(успех {fetched}, ошибок {errors})"
            )

    # Финальная очистка
    buffer.clear()
    gc.collect()

    logger.info(f"✅ Ozon refresh complete: fetched={fetched}, errors={errors}")
    return {
        "platform": "ozon",
        "fetched": fetched,
        "errors": errors,
        "error_details": error_details,
    }
