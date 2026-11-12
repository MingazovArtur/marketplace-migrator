"""Предпросмотр файла импорта: первые строки + ошибки парсинга (без записи в БД).

Вынесено без изменений из монолита routers/import_router.py (Р13).
"""

import asyncio
import logging

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
from parsers import preview_file
from routers.import_router._support import MAX_IMPORT_FILE_SIZE

logger = logging.getLogger(__name__)
router = APIRouter()

# ==================== ПРЕДПРОСМОТР ФАЙЛА ====================
@limiter.limit("30/minute")
@router.post("/import/preview")
async def preview_import(
    request: Request,
    platform: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Предпросмотр файла: первые строки + ошибки парсинга (без записи в БД)."""
    if platform not in PLATFORM_CONFIG:
        raise HTTPException(status_code=400, detail=f"Неизвестная платформа: {platform}")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")

    fname_lower = file.filename.lower()
    if not (fname_lower.endswith(".csv") or fname_lower.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .csv и .xlsx")
    file_type = "csv" if fname_lower.endswith(".csv") else "xlsx"

    try:
        contents = await file.read()
        if len(contents) > MAX_IMPORT_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 15 МБ)")
        preview_data = await asyncio.to_thread(
            preview_file, contents, platform, file_type, max_rows=10
        )
        return {"success": True, "preview": preview_data}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка предпросмотра: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
