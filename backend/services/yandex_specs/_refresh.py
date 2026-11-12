"""Оркестратор refresh_yandex_specs: чанки, пауза/продолжение, прогресс."""

import asyncio
import gc
import logging
from collections.abc import Callable

import httpx

from services.yandex_specs._http import CONCURRENCY, TIMEOUT, _ym_headers
from services.yandex_specs._parameters import (
    YM_BASE_REQUIRED_FIELDS,
    _build_validation_rules,
    fetch_yandex_category_parameters,
)
from services.yandex_specs._storage import DB_CHUNK, _flush_ym_buffer
from services.yandex_specs._tree import fetch_yandex_categories_tree

logger = logging.getLogger(__name__)

PROGRESS_EVERY = 10


async def refresh_yandex_specs(
    user_id: int,
    token: str,
    business_id: str | None = None,
    category_ids: list[str] | None = None,
    progress_cb: Callable | None = None,
    concurrency: int = CONCURRENCY,
    skip_category_ids: list[str] | None = None,
    pause_check: Callable[[], bool] | None = None,
    done_keys: set | None = None,
) -> dict:
    """
    Загружает дерево категорий Яндекс Маркета и их характеристики,
    сохраняя в platform_category_specs.
    При остановке админом возвращает {"paused": True, ...} —
    skip_category_ids (ключи = category_id) пропускаются, done_keys
    наполняется успешно сохранёнными (для продолжения после паузы).
    """
    if not token or not token.strip():
        raise ValueError("Не указан API-ключ Яндекс Маркета (формат ACMA:...)")

    headers = _ym_headers(token)
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency + 4, max_keepalive_connections=concurrency)

    fetched = 0
    errors = 0
    error_details: list[dict] = []
    done_count = 0
    buffer: list[tuple[dict, dict]] = []

    async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits) as client:
        leaves = await fetch_yandex_categories_tree(client, sem, headers)

        if category_ids:
            wanted = {str(c).strip() for c in category_ids if str(c).strip()}
            leaves = [
                leaf
                for leaf in leaves
                if leaf["id"] in wanted
                or leaf["name"].lower() in {w.lower() for w in wanted}
            ]

        # Продолжение после паузы: пропускаем уже сохранённые категории
        if skip_category_ids:
            skip = {str(c) for c in skip_category_ids}
            before = len(leaves)
            leaves = [leaf for leaf in leaves if str(leaf["id"]) not in skip]
            if before != len(leaves):
                logger.info(f"⏩ Яндекс: пропущено {before - len(leaves)} категорий из прошлой загрузки")

        total = len(leaves)
        logger.info(
            f"🚀 Яндекс Маркет: к загрузке {total} категорий (business_id={business_id})"
        )

        if progress_cb:
            progress_cb({"total": total, "fetched": 0, "errors": 0})

        if total == 0:
            return {
                "platform": "yandex",
                "fetched": 0,
                "errors": 0,
                "error_details": [],
            }

        async def work(leaf: dict) -> None:
            nonlocal fetched, errors, done_count
            try:
                attrs = await fetch_yandex_category_parameters(client, sem, headers, leaf["id"])
                spec_content = {
                    "sheets": ["Список товаров", "Инструкция"],
                    "required_fields": YM_BASE_REQUIRED_FIELDS
                    + [a["name"] for a in attrs if a["required"]],
                    "attributes": attrs,
                    "validation_rules": _build_validation_rules(attrs),
                    "special_requirements": {
                        "yandex_category_name": leaf["name"],
                        "yandex_category_id": leaf["id"],
                    },
                }
                buffer.append((leaf, spec_content))
                fetched += 1
            except Exception as e:
                errors += 1
                if len(error_details) < 50:
                    error_details.append({"category_id": leaf["id"], "error": str(e)[:300]})
            finally:
                done_count += 1
                if progress_cb and (done_count % PROGRESS_EVERY == 0 or done_count == total):
                    progress_cb({"total": total, "fetched": fetched, "errors": errors})

        for i in range(0, total, DB_CHUNK):
            # Кооперативная пауза между блоками: блок дообрабатывается и коммитится
            if pause_check and pause_check():
                logger.info(f"⏸ Яндекс: пауза на {done_count}/{total} — блоки до сюда сохранены")
                return {
                    "platform": "yandex",
                    "paused": True,
                    "fetched": fetched,
                    "errors": errors,
                    "error_details": error_details,
                }

            chunk = leaves[i : i + DB_CHUNK]
            await asyncio.gather(*(work(leaf) for leaf in chunk))
            flushed = list(buffer)
            try:
                _flush_ym_buffer(user_id, buffer)
                if done_keys is not None:
                    done_keys.update(str(leaf["id"]) for leaf, _ in flushed)
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения чанка Яндекс Маркета: {e}")
                errors += len(buffer)
            buffer.clear()
            gc.collect()

    return {
        "platform": "yandex",
        "fetched": fetched,
        "errors": errors,
        "error_details": error_details,
    }
