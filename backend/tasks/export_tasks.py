"""Тяжёлый XLSX-экспорт в выделенной очереди xlsx_export (изолирует openpyxl)."""

import logging
import time
from pathlib import Path

from celery_app import celery_app
from services.xlsx_generator import generate_export

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path("/app/media/exports")


def _ensure_exports_dir() -> Path:
    """Создаёт каталог экспортов при первом запуске задачи (без side-effect на импорте)."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORTS_DIR


@celery_app.task(bind=True, name="tasks.generate_xlsx_export_task")
def generate_xlsx_export_task(
    self, products: list, specs_by_category: dict, platform: str, user_id: int
):
    """
    Фоновая генерация тяжёлых XLSX/ZIP отчётов и шаблонов в выделенной очереди xlsx_export.
    Изолирует openpyxl от основного веб-процесса FastAPI.
    """
    t0 = time.perf_counter()
    total = len(products)
    logger.info(
        f"📊 Старт фоновой генерации XLSX для платформы '{platform}' (товаров: {total}, user={user_id})"
    )

    self.update_state(
        state="PROGRESS",
        meta={
            "total": total,
            "done": 0,
            "percent": 0,
            "message": "Сборка структуры openpyxl...",
            # Владелец в meta — для IDOR-проверки статуса задачи до её завершения
            # (get_progress эти поля наружу не отдаёт)
            "user_id": user_id,
        },
    )

    try:
        data, filename = generate_export(products, specs_by_category, platform)

        # Сохранение файла на общий том /app/media/exports
        file_path = _ensure_exports_dir() / f"{self.request.id}_{filename}"
        with open(file_path, "wb") as f:
            f.write(data)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            f"✅ XLSX успешно сгенерирован в Celery: {filename} ({len(data)} байт, {duration_ms} мс)"
        )

        return {
            "status": "completed",
            "filename": filename,
            "file_path": str(file_path),
            "size": len(data),
            "total": total,
            "percent": 100,
            "duration_ms": duration_ms,
            # IDOR-защита (В-2): владелец проверяется при скачивании/статусе,
            # fallback для случая, когда Redis-ключ уже истёк
            "user_id": user_id,
        }
    except Exception as e:
        logger.error(f"❌ Ошибка генерации XLSX в Celery: {e}", exc_info=True)
        raise e
