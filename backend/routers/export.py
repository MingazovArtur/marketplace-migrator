"""
Роутер экспорта: выгрузка файлов для ЛК площадок, предпросмотр, валидация, шаблоны.
"""
import io
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
from database.repository import repo, op_log
from database.models import User
from core.auth import get_current_user
from core.platforms import Platform
from services.export_builder import build_upload_file, build_rows
from services.export_validator import validate_products, validate_product, has_errors
import time
from database.repository import repo, op_log, stats_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Export"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _get_products_for_export(current_user: User, status: str) -> list:
    is_admin = current_user.role == "admin"
    result = repo.get_all(user_id=current_user.id, is_admin=is_admin, limit=10000)
    products = result["products"]
    if status != "all":
        products = [p for p in products if p["status"] == status]
    return products


@router.get("/export/preview/{platform}")
def export_preview(
    platform: str,
    status: str = "success",
    current_user: User = Depends(get_current_user),
):
    """Предпросмотр выгрузки: первые 10 строк файла + сводка валидации."""
    if platform not in Platform.all_values():
        raise HTTPException(status_code=404, detail=f"Платформа '{platform}' не найдена")

    products = _get_products_for_export(current_user, status)
    if not products:
        return {
            "success": True, "columns": [], "rows": [],
            "validation": {"total": 0, "ready": 0, "with_warnings": 0, "with_errors": 0, "issues": []},
        }

    validation = validate_products(products, platform)
    rows = build_rows(products[:10], platform)
    columns = list(rows[0].keys()) if rows else []

    return {"success": True, "columns": columns, "rows": rows, "validation": validation}


@router.get("/export/template/{platform}")
def export_template(
    platform: str,
    current_user: User = Depends(get_current_user),
):
    """Пустой шаблон выгрузки с примером строки и листом-инструкцией."""
    if platform not in Platform.all_values():
        raise HTTPException(status_code=404, detail=f"Платформа '{platform}' не найдена")

    sample = {
        "id": 1,
        "name": "Футболка детская, хлопок 100%, размеры 92-128",
        "price": 990,
        "mapped_category": "Одежда",
        "category": "Одежда",
        "photos": ["https://example.com/photo1.jpg", "https://example.com/photo2.jpg"],
        "description": "Качественная детская футболка из натурального хлопка.",
        "stock": 10,
    }
    rows = build_rows([sample], platform)
    df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Товары")
        ws = writer.sheets["Товары"]
        for i, col in enumerate(df.columns):
            ws.column_dimensions[chr(65 + i)].width = 30

        instructions = pd.DataFrame({"Инструкция": [
            f"Шаблон выгрузки для {platform}",
            "1. Заполняйте по одной строке на товар.",
            "2. Не меняйте заголовки колонок и имена листов.",
            "3. Фото указывайте прямыми ссылками через '; '.",
            "4. Готовый файл загрузите в личном кабинете площадки.",
        ]})
        instructions.to_excel(writer, index=False, sheet_name="Инструкция")
        writer.sheets["Инструкция"].column_dimensions["A"].width = 80

    output.seek(0)
    filename = f"template_{platform}.xlsx"
    return StreamingResponse(
        output, media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/platform/{platform}")
def export_for_platform(
    platform: str,
    status: str = "success",
    current_user: User = Depends(get_current_user),):
    """Файл XLSX для загрузки в ЛК площадки. Товары с ошибками валидации исключаются."""
    if platform not in Platform.all_values():
        raise HTTPException(status_code=404, detail=f"Платформа '{platform}' не найдена")

    products = _get_products_for_export(current_user, status)

    valid_products = []
    skipped = []
    for p in products:
        issues = validate_product(p, platform)
        if has_errors(issues):
            skipped.append(p["id"])
        else:
            valid_products.append(p)

    if skipped:
        logger.warning(f"⚠️ Исключено из выгрузки {len(skipped)} товаров с ошибками: {skipped[:10]}")
    if not valid_products:
        raise HTTPException(
            status_code=400,
            detail="Нет товаров, прошедших валидацию (проверьте цены и названия)",
        )

    try:
        output = build_upload_file(valid_products, platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filename = f"upload_{platform}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    op_log.log_file_operation(
        user_id=current_user.id, operation="export", platform=platform,
        filename=filename, status="success", total_rows=len(valid_products),
        imported=0, updated=0, failed=len(skipped),
        errors=[{"product_id": i, "error": "исключён: ошибки валидации"} for i in skipped[:10]],
    )

    t0 = time.perf_counter()
    stats_repo.record(
        user_id=current_user.id,
        operation="export",
        platform=platform,
        status="success",
        total_items=len(valid_products),
        success_items=len(valid_products),
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
    return StreamingResponse(
        output, media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/report")
def export_migration_report(current_user: User = Depends(get_current_user)):
    """Excel-отчёт по товарам текущего пользователя."""
    is_admin = current_user.role == "admin"
    result = repo.get_all(user_id=current_user.id, is_admin=is_admin, limit=10000)
    products = result["products"]

    data = []
    for p in products:
        data.append({
            "ID": p["id"],
            "Название товара": p["name"],
            "Артикул (SKU)": p.get("sku") or f"SKU-{p['id']}",
            "Источник": p["source"],
            "Цена (₽)": p["price"],
            "Категория (источник)": p.get("category") or "Не указана",
            "Категория (назначение)": p.get("mapped_category") or "Не маппировалось",
            "Статус": p["status"],
            "Ошибка": p.get("error_message") or "",
            "Дата выгрузки": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    df = pd.DataFrame(data)
    if df.empty:
        df = pd.DataFrame(columns=[
            "ID", "Название товара", "Артикул (SKU)", "Источник", "Цена (₽)",
            "Категория (источник)", "Категория (назначение)", "Статус", "Ошибка", "Дата выгрузки",
        ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Отчет миграции")
        ws = writer.sheets["Отчет миграции"]
        ws.column_dimensions["B"].width = 40
        ws.column_dimensions["D"].width = 25

    output.seek(0)
    filename = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    logger.info(f"Сформирован отчёт Excel: {len(data)} строк для пользователя {current_user.username}")

    return StreamingResponse(
        output, media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )