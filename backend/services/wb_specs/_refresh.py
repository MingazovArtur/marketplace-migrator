"""Оркестратор refresh_wildberries_specs: пауза перед каждым предметом, задержка, прогресс."""

import asyncio
import logging
from collections.abc import Callable

import httpx

from services.wb_specs._characteristics import (
    _build_special_requirements,
    _build_validation_rules,
    fetch_wb_characteristics,
)
from services.wb_specs._storage import _upsert_spec
from services.wb_specs._subjects import fetch_wb_subjects

logger = logging.getLogger(__name__)

# Пауза между запросами характеристик — бережём rate-limit WB[cite: 12]
WB_REQUEST_DELAY = 0.2
PROGRESS_EVERY = 5


async def refresh_wildberries_specs(
    user_id: int,
    token: str,
    category_ids: list[str] | None = None,
    progress_cb: Callable | None = None,
    skip_category_ids: list[str] | None = None,
    pause_check: Callable[[], bool] | None = None,
    done_keys: set | None = None,
) -> dict:
    """
    Подтягивает предметы + характеристики, сохраняет как PlatformCategorySpec.
    При остановке админом возвращает {"paused": True, ...};
    skip_category_ids (ключи = objectID предмета) пропускаются,
    done_keys наполняется сохранёнными (для продолжения после паузы).
    """
    async with httpx.AsyncClient(timeout=60) as client:
        subjects = await fetch_wb_subjects(client, token)

        if category_ids:
            subjects = [s for s in subjects if s["id"] in category_ids]

        # Продолжение после паузы: пропускаем уже сохранённые предметы
        if skip_category_ids:
            skip = {str(c) for c in skip_category_ids}
            before = len(subjects)
            subjects = [s for s in subjects if str(s["id"]) not in skip]
            if before != len(subjects):
                logger.info(
                    f"⏩ WB: пропущено {before - len(subjects)} предметов из прошлой загрузки"
                )

        total = len(subjects)
        fetched = 0
        errors = []

        if progress_cb:
            progress_cb({"total": total, "fetched": 0, "errors": 0})

        for idx, s in enumerate(subjects, start=1):
            # Кооперативная пауза перед каждым предметом (отклик почти мгновенный)
            if pause_check and pause_check():
                logger.info(f"⏸ WB: пауза на {idx - 1}/{total} — сделанное сохранено в БД")
                return {
                    "platform": "wildberries",
                    "paused": True,
                    "fetched": fetched,
                    "errors": len(errors),
                    "error_details": errors[:20],
                }

            try:
                attrs = await fetch_wb_characteristics(client, token, s["id"])

                spec_content = {
                    # WB Excel-выгрузка из редактора карточек — один лист[cite: 12]
                    "sheets": ["Товары"],
                    "required_fields": [a["name"] for a in attrs if a["required"]],
                    "attributes": attrs,
                    "validation_rules": _build_validation_rules(attrs),
                    "special_requirements": _build_special_requirements(),
                }

                _upsert_spec(
                    user_id=user_id,
                    platform="wildberries",
                    category_id=s["id"],
                    category_name=s["name"],
                    parent_category_id=s["parent_id"],
                    spec=spec_content,
                )
                fetched += 1
                if done_keys is not None:
                    done_keys.add(str(s["id"]))
            except Exception as e:
                errors.append({"category_id": s["id"], "error": str(e)})
                logger.warning(f"WB: ошибка загрузки характеристик предмета {s['id']}: {e}")

            if progress_cb and (idx % PROGRESS_EVERY == 0 or idx == total):
                progress_cb({"total": total, "fetched": fetched, "errors": len(errors)})

            await asyncio.sleep(WB_REQUEST_DELAY)  # бережём rate-limit[cite: 12]

    return {
        "platform": "wildberries",
        "fetched": fetched,
        "errors": len(errors),
        "error_details": errors[:20],
    }
