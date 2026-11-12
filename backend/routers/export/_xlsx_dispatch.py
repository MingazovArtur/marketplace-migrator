"""
Диспетчер генерации XLSX: очередь Celery `xlsx_export` или резервный поток.

Вынесено из монолита routers/export.py (Р1). Порог/таймаут — в _support.
"""

import asyncio
import contextlib
import logging
import time
from pathlib import Path

from routers.export._support import CELERY_XLSX_THRESHOLD, CELERY_XLSX_TIMEOUT_SEC
from services.xlsx_generator import generate_export
from tasks import generate_xlsx_export_task

logger = logging.getLogger(__name__)


async def run_xlsx_via_celery_or_thread(
    product_dicts: list[dict],
    specs_by_category: dict,
    platform: str,
    user_id: int,
    force_celery: bool = False,
) -> tuple[bytes, str]:
    """
    Выполняет генерацию XLSX:
      - Если товаров >= CELERY_XLSX_THRESHOLD (или force_celery=True), отправляет задачу
        в изолированную очередь `xlsx_export` и неблокирующе ждёт файл.
      - Для малых партий (или при недоступности воркера) выполняет генерацию в отдельном
        потоке через asyncio.to_thread, не блокируя event loop FastAPI.
    """
    use_celery = force_celery or len(product_dicts) >= CELERY_XLSX_THRESHOLD

    if use_celery:
        try:
            async_res = generate_xlsx_export_task.apply_async(
                args=[product_dicts, specs_by_category, platform, user_id],
                queue="xlsx_export",
            )
            deadline = time.monotonic() + CELERY_XLSX_TIMEOUT_SEC
            while time.monotonic() < deadline:
                if async_res.ready():
                    if async_res.successful():
                        res_data = async_res.result or {}
                        file_path = res_data.get("file_path")
                        filename = res_data.get("filename") or f"{platform}_export.xlsx"
                        if file_path and Path(file_path).is_file():
                            data = await asyncio.to_thread(Path(file_path).read_bytes)
                            with contextlib.suppress(Exception):
                                await asyncio.to_thread(Path(file_path).unlink, True)
                            return data, filename
                    break
                await asyncio.sleep(0.25)
            logger.warning(
                f"⚠️ Celery xlsx_export не ответил вовремя для task={async_res.id}, "
                f"переключаюсь на резервную сборку в asyncio.to_thread"
            )
        except Exception as e:
            logger.warning(
                f"⚠️ Не удалось отправить задачу в очередь xlsx_export ({e}), "
                f"выполняю через asyncio.to_thread"
            )

    return await asyncio.to_thread(
        generate_export, product_dicts, specs_by_category, platform
    )
