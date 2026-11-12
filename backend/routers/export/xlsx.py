"""
XLSX v2: выгрузка по эталонному шаблону с изоляцией в очереди Celery `xlsx_export`,
async-постановка, статус и скачивание фоновых задач (с IDOR-защитой).

Вынесено из монолита routers/export.py (Р1). Дублированные inline-выборки
заменены общим load_user_products; поведение фильтров сохранено.
"""

import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from celery_app import celery_app
from core.auth import get_current_user
from core.rate_limit import limiter
from database.models import User
from database.repository import stats_repo
from database.session import get_async_db
from routers.export._queries import (
    load_specs_by_category,
    load_user_products,
    mark_exported,
    product_to_dict,
)
from routers.export._support import (
    XLSX_MIME,
    assert_export_task_owner,
    parse_product_ids,
    register_export_task_owner,
    safe_disposition,
)
from routers.export._xlsx_dispatch import run_xlsx_via_celery_or_thread
from tasks import generate_xlsx_export_task, get_progress

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_STATUSES = ("success", "pending", "processing", "error", "all")


@limiter.limit("30/minute")
@router.get("/export/xlsx/{platform}")
async def export_xlsx_v2(
    request: Request,
    platform: str,
    status: str = "success",
    product_id: int = Query(None),
    product_ids: str = Query(None),
    use_celery: bool = Query(False, description="Принудительно собрать файл в очереди xlsx_export"),
    changed_since: bool = Query(False, description="✅ v4: только изменённые с последней выгрузки"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    XLSX v2: выгрузка по эталонному шаблону площадки (Ozon, Яндекс Маркет, WB, Магнит).
    Тяжёлые выгрузки автоматически изолируются в очереди Celery `xlsx_export`.
    """
    if not status or status not in _ALLOWED_STATUSES:
        status = "success"

    ids = parse_product_ids(product_id, product_ids)
    if ids:
        logger.info(f"📥 Экспорт выбранных товаров: ids={ids}, platform={platform}")

    products = await load_user_products(
        db, current_user, status, selected_ids=ids, changed_since=changed_since
    )

    if not products:
        detail = (
            f"Выбранные товары ({ids}) не найдены"
            if ids
            else (
                "Нет новых/изменённых товаров с последней выгрузки — выгружать нечего"
                if changed_since
                else f"Нет товаров со статусом '{status}'. Импортируйте товары и выполните миграцию."
            )
        )
        raise HTTPException(status_code=400, detail=detail)

    product_dicts = [product_to_dict(p) for p in products]
    specs_by_category = await load_specs_by_category(db, product_dicts, platform)

    t0 = time.perf_counter()
    data, filename = await run_xlsx_via_celery_or_thread(
        product_dicts=product_dicts,
        specs_by_category=specs_by_category,
        platform=platform,
        user_id=current_user.id,
        force_celery=use_celery,
    )

    stats_repo.record(
        user_id=current_user.id,
        operation="export",
        platform=platform,
        status="success",
        total_items=len(product_dicts),
        success_items=len(product_dicts),
        failed_items=0,
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )

    media = "application/zip" if filename.endswith(".zip") else XLSX_MIME

    # ✅ v4: пометить выгруженные товары (для последующих «только изменённые»)
    await mark_exported(db, [p["id"] for p in product_dicts], platform)

    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": safe_disposition(filename)},
    )


@limiter.limit("30/minute")
@router.post("/export/xlsx/{platform}/async")
async def start_async_xlsx_export(
    request: Request,
    platform: str,
    status: str = "success",
    product_id: int = Query(None),
    product_ids: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Постановка генерации тяжёлого XLSX/ZIP файла в выделенную очередь Celery `xlsx_export`.
    Возвращает task_id для отслеживания прогресса и скачивания через /export/tasks/{task_id}/download.
    """
    if not status or status not in _ALLOWED_STATUSES:
        status = "success"

    ids = parse_product_ids(product_id, product_ids)
    products = await load_user_products(db, current_user, status, selected_ids=ids)
    if not products:
        raise HTTPException(status_code=400, detail="Нет товаров для выгрузки")

    product_dicts = [product_to_dict(p) for p in products]
    specs_by_category = await load_specs_by_category(db, product_dicts, platform)

    task = generate_xlsx_export_task.apply_async(
        args=[product_dicts, specs_by_category, platform, current_user.id],
        queue="xlsx_export",
    )
    # IDOR-защита (В-2): привязываем task_id к владельцу
    register_export_task_owner(task.id, current_user.id)
    return {
        "task_id": task.id,
        "status": "pending",
        "total": len(product_dicts),
        "queue": "xlsx_export",
    }


@router.get("/export/tasks/{task_id}")
async def get_export_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Статус фоновой задачи генерации XLSX (только владелец задачи или админ)."""
    assert_export_task_owner(task_id, current_user)
    return get_progress(task_id)


@router.get("/export/tasks/{task_id}/download")
async def download_export_task_file(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Скачивание готового XLSX/ZIP файла, сгенерированного воркером очереди xlsx_export.
    Только владелец задачи или админ (было В-2 код-ревью: IDOR — любой
    авторизованный пользователь мог скачать чужой файл по task_id).
    """
    assert_export_task_owner(task_id, current_user)

    res = celery_app.AsyncResult(task_id)
    if not res.ready():
        raise HTTPException(status_code=409, detail="Файл ещё формируется")
    if not res.successful():
        raise HTTPException(status_code=500, detail="Ошибка при генерации файла в воркере")

    info = res.result or {}
    file_path = info.get("file_path")
    filename = info.get("filename") or "export.xlsx"

    if not file_path or not Path(file_path).is_file():
        raise HTTPException(status_code=404, detail="Сгенерированный файл не найден или уже скачан")

    media = "application/zip" if filename.endswith(".zip") else XLSX_MIME
    return FileResponse(
        path=file_path,
        media_type=media,
        filename=filename,
        headers={"Content-Disposition": safe_disposition(filename)},
    )
