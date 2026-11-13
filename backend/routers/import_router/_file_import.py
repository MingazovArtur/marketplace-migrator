"""Импорт товаров из файла (XLSX / CSV): POST /import/file.

mode=upsert — обновляет существующие карточки по external_id/sku вместо
дублей; варианты (SKU) и характеристики (attributes) из файла сохраняются
в связанные таблицы.

Вынесено без изменений из монолита routers/import_router.py (Р13).
"""

import asyncio
import logging
import time

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)

from core.auth import get_current_user
from core.platforms import PLATFORM_CONFIG
from core.rate_limit import limiter
from database.models import User
from database.repository import op_log, stats_repo
from parsers import parse_file
from routers.import_router._support import (
    MAX_IMPORT_FILE_SIZE,
    _persist_imported_products,
    _source_label,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== ИМПОРТ ИЗ ФАЙЛА (XLSX / CSV) ====================
@limiter.limit("10/minute;100/day")
@router.post("/import/file")
async def import_from_file(
    request: Request,
    platform: str = Form(...),
    mode: str = Form("create"),  # create | upsert
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Импорт товаров из Excel (.xlsx) или CSV.
    mode=upsert — обновляет существующие карточки по external_id/sku вместо дублей.
    Варианты (SKU) и характеристики (attributes) из файла сохраняются в связанные таблицы.
    """
    t0 = time.perf_counter()

    if platform not in PLATFORM_CONFIG:
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform}")
    if mode not in ("create", "upsert"):
        raise HTTPException(status_code=400, detail="Режим должен быть create или upsert")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")

    fname_lower = file.filename.lower()
    if not (fname_lower.endswith(".csv") or fname_lower.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .csv и .xlsx")
    file_type = "csv" if fname_lower.endswith(".csv") else "xlsx"

    # ---------- Парсинг ----------
    try:
        contents = await file.read()
        if len(contents) > MAX_IMPORT_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 15 МБ)")
        # openpyxl — CPU-bound, выносим в threadpool, чтобы не блокировать event loop (B-1)
        result = await asyncio.to_thread(parse_file, contents, platform, file_type)
    except HTTPException:
        raise
    except ValueError as e:
        stats_repo.record(
            user_id=current_user.id,
            operation="import_file",
            platform=platform,
            status="error",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Ошибка парсинга файла: {e}")
        stats_repo.record(
            user_id=current_user.id,
            operation="import_file",
            platform=platform,
            status="error",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise HTTPException(
            status_code=500, detail="Внутренняя ошибка сервера при обработке файла"
        ) from e

    products_data = result["products"]
    errors = result["errors"]

    if not products_data:
        op_log.log_file_operation(
            user_id=current_user.id,
            operation="import_file",
            platform=platform,
            filename=file.filename,
            mode=mode,
            status="error",
            total_rows=result["total_rows"],
            imported=0,
            updated=0,
            failed=len(errors),
            errors=errors[:10],
        )
        stats_repo.record(
            user_id=current_user.id,
            operation="import_file",
            platform=platform,
            status="error",
            total_items=result["total_rows"],
            success_items=0,
            failed_items=len(errors),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise HTTPException(
            status_code=400, detail="Не найдено валидных товаров в файле. Проверьте ошибки."
        )

    # ---------- Запись в БД ----------
    # Синхронные repo-записи вынесены в threadpool: event loop не блокируется
    # на время записи сотен товаров (B-1, неделя 2)
    source_label = _source_label(platform)
    imported, updated = await asyncio.to_thread(
        _persist_imported_products, current_user.id, source_label, mode, products_data
    )

    logger.info(
        f"✅ Импорт завершён: создано {imported}, обновлено {updated}, ошибок {len(errors)}",
        extra={"user_id": current_user.id, "platform": platform},
    )

    # ---------- Логирование ----------
    warnings = result.get("warnings", [])
    message = f"Импорт завершён: создано {imported}, обновлено {updated}"
    if warnings:
        message += ". " + " ".join(w["message"] for w in warnings)

    status_val = "success" if not errors else "partial"

    op_log.log_file_operation(
        user_id=current_user.id,
        operation="import_file",
        platform=platform,
        filename=file.filename,
        mode=mode,
        status=status_val,
        total_rows=result["total_rows"],
        imported=imported,
        updated=updated,
        failed=len(errors),
        errors=errors[:10],
    )
    stats_repo.record(
        user_id=current_user.id,
        operation="import_file",
        platform=platform,
        status=status_val,
        total_items=result["total_rows"],
        success_items=imported + updated,
        failed_items=len(errors),
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )

    return {
        "success": True,
        "message": message,
        "imported": imported,
        "updated": updated,
        "total_rows": result["total_rows"],
        "failed": len(errors),
        "errors": errors[:20],
        "warnings": warnings,
    }
