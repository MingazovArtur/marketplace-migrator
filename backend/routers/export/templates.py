"""
Эталонные шаблоны площадок (мультиплатформенные): загрузка/листинг/мета/
статус/скачивание/удаление.

Вынесено из монолита routers/export.py (Р1).
"""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_admin_user, get_current_user
from database.models import User
from database.session import get_async_db
from routers.export._queries import normalize_category_name
from routers.export._support import XLSX_MIME, safe_disposition
from services import template_filler

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/export/ozon-template/upload")
async def upload_official_template(
    request: Request,
    category_name: str = Form("Универсальный (все категории)"),
    platform: str = Form("ozon"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Приём эталонного XLSX-шаблона для любой площадки (Ozon, Яндекс Маркет, WB, Магнит).

    Только для администраторов (было В-2 код-ревью): эталон влияет на
    экспорт ВСЕХ пользователей — перезаписывать его рядовым пользователям нельзя.
    """
    pl = (platform or "ozon").lower().strip()
    cat = await normalize_category_name(db, category_name, pl)

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400, detail="Нужен файл .xlsx — шаблон из кабинета площадки"
        )

    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл больше 15 МБ")

    problem = template_filler.validate_template_bytes(data, platform=pl)
    if problem:
        raise HTTPException(status_code=400, detail=f"Это не валидный шаблон {pl}: {problem}")

    meta = template_filler.save_official_template(
        cat, data, uploaded_by=current_user.username, platform=pl
    )
    return {
        "ok": True,
        "platform": pl,
        "category": cat,
        "size": len(data),
        "columns": meta.get("columns"),
        "message": f"Эталон [{pl}] для «{cat}» сохранён ({meta.get('columns')} колонок).",
    }


@router.get("/export/ozon-template/list")
async def list_official_templates(
    platform: str = Query("ozon"),
    current_user: User = Depends(get_current_user),
):
    return {"templates": template_filler.list_template_names(platform=platform)}


@router.get("/export/ozon-template/meta")
async def list_official_templates_meta(current_user: User = Depends(get_current_user)):
    return {"templates": template_filler.list_official_templates()}


@router.get("/export/ozon-template/status")
async def ozon_template_status(
    category_name: str = "Универсальный (все категории)",
    platform: str = Query("ozon"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    pl = (platform or "ozon").lower().strip()
    cat = await normalize_category_name(db, category_name, pl)
    meta = template_filler.get_template_meta(cat, platform=pl)
    return {
        "platform": pl,
        "category": cat,
        "has_official_template": meta is not None,
        "meta": meta,
    }


@router.get("/export/ozon-template/download")
async def download_official_template(
    category_name: str = "Универсальный (все категории)",
    platform: str = Query("ozon"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    pl = (platform or "ozon").lower().strip()
    cat = await normalize_category_name(db, category_name, pl)
    data = template_filler.read_template_bytes(cat, platform=pl)
    if not data:
        raise HTTPException(status_code=404, detail=f"Эталон для «{cat}» [{pl}] не найден")
    fname = f"{pl}_{cat.replace('/', '_').strip()}.xlsx"
    return Response(
        content=data,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": safe_disposition(fname)},
    )


@router.delete("/export/ozon-template")
async def delete_official_template(
    category_name: str = "Универсальный (все категории)",
    platform: str = Query("ozon"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Удаление эталона — только админ (было В-2 код-ревью: мог любой пользователь)."""
    pl = (platform or "ozon").lower().strip()
    cat = await normalize_category_name(db, category_name, pl)
    deleted = template_filler.delete_official_template(cat, platform=pl)
    if not deleted:
        raise HTTPException(status_code=404, detail="Эталон не найден")
    logger.info(f"🗑 Эталон [{pl}] удалён: '{cat}' (пользователь {current_user.username})")
    return {"ok": True, "platform": pl, "category": cat}
