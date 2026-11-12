"""
Файлы выгрузки: шаблон с инструкцией, готовый файл для ЛК площадки,
отчёт по всем товарам.

Вынесено из монолита routers/export.py (Р1).
"""

import asyncio
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.platforms import Platform
from core.rate_limit import limiter
from database.models import User
from database.repository import op_log
from database.session import get_async_db
from routers.export._queries import (
    get_products_for_export_async,
    mark_exported,
)
from routers.export._support import XLSX_MIME, parse_product_ids, safe_disposition
from services.export_builder import build_rows, build_upload_file
from services.export_validator import has_errors, validate_product
from services.xlsx_io import rows_workbook, write_columns

router = APIRouter()


@limiter.limit("10/minute")
@router.get("/export/template/{platform}")
async def export_template(
    request: Request,
    platform: str,
    current_user: User = Depends(get_current_user),
):
    if platform not in Platform.all_values():
        raise HTTPException(status_code=404, detail=f"Платформа '{platform}' не найдена")

    # AliExpress и Мегамаркет: шаблон-пример в структуре официального XLSX площадки
    if platform in ("aliexpress", "megamarket"):
        if platform == "aliexpress":
            from services.xlsx_generator.aliexpress import (
                aliexpress_example_products,
                build_aliexpress_workbook,
            )

            wb = build_aliexpress_workbook(aliexpress_example_products())
        else:
            from services.xlsx_generator.megamarket import (
                build_megamarket_workbook,
                megamarket_example_products,
            )

            wb = build_megamarket_workbook(megamarket_example_products())

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        filename = f"template_{platform}.xlsx"
        return StreamingResponse(
            output,
            media_type=XLSX_MIME,
            headers={"Content-Disposition": safe_disposition(filename)},
        )

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

    wb = rows_workbook(rows, "Товары")
    ws = wb["Товары"]
    for i, _col in enumerate(ws[1]):
        ws.column_dimensions[chr(65 + i)].width = 30

    instructions = {
        "Инструкция": [
            f"Шаблон выгрузки для {platform}",
            "1. Заполняйте по одной строке на товар.",
            "2. Не меняйте заголовки колонок и имена листов.",
            "3. Фото указывайте прямыми ссылками через '; '.",
            "4. Готовый файл загрузите в личном кабинете площадки.",
        ]
    }
    write_columns(wb, "Инструкция", instructions)
    wb["Инструкция"].column_dimensions["A"].width = 80

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"template_{platform}.xlsx"
    return StreamingResponse(
        output,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": safe_disposition(filename)},
    )


@limiter.limit("10/minute;100/day")
@router.get("/export/platform/{platform}")
async def export_for_platform(
    request: Request,
    platform: str,
    status: str = "success",
    product_id: int = Query(None),
    product_ids: str = Query(None),
    changed_since: bool = Query(False, description="✅ v4: только изменённые с последней выгрузки"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    if platform not in Platform.all_values():
        raise HTTPException(status_code=404, detail=f"Платформа '{platform}' не найдена")

    ids = parse_product_ids(product_id, product_ids)
    products = await get_products_for_export_async(
        db, current_user, status, selected_ids=ids, changed_since=changed_since
    )

    if changed_since and not products:
        raise HTTPException(
            status_code=400,
            detail="Нет новых/изменённых товаров с последней выгрузки — выгружать нечего",
        )

    valid_products, skipped = [], []
    for p in products:
        issues = validate_product(p, platform)
        if has_errors(issues):
            skipped.append(p["id"])
        else:
            valid_products.append(p)

    if not valid_products:
        raise HTTPException(
            status_code=400,
            detail="Нет товаров, прошедших валидацию (проверьте цены и названия)",
        )

    try:
        output = await asyncio.to_thread(build_upload_file, valid_products, platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    filename = f"upload_{platform}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    op_log.log_file_operation(
        user_id=current_user.id,
        operation="export",
        platform=platform,
        filename=filename,
        status="success",
        total_rows=len(valid_products),
        imported=0,
        updated=0,
        failed=len(skipped),
        errors=[{"product_id": i, "error": "исключён: ошибки валидации"} for i in skipped[:10]],
    )

    # ✅ v4: пометить выгруженные товары (для «только изменённые»)
    await mark_exported(db, [p["id"] for p in valid_products], platform)

    return StreamingResponse(
        output,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": safe_disposition(filename)},
    )


@limiter.limit("5/minute;50/day")
@router.get("/export/report")
async def export_migration_report(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    products = await get_products_for_export_async(
        db, current_user, status="all", selected_ids=None, limit=10000
    )

    data = []
    for p in products:
        data.append(
            {
                "ID": p["id"],
                "Название товара": p["name"],
                "Артикул (SKU)": p.get("sku") or f"SKU-{p['id']}",
                "Источник": p.get("source") or "",
                "Цена (₽)": p["price"],
                "Категория (источник)": p.get("category") or "Не указана",
                "Категория (назначение)": p.get("mapped_category") or "Не маппировалось",
                "Статус": p.get("status") or "",
                "Ошибка": p.get("error_message") or "",
                "Дата выгрузки": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    df_columns = [
        "ID",
        "Название товара",
        "Артикул (SKU)",
        "Источник",
        "Цена (₽)",
        "Категория (источник)",
        "Категория (назначение)",
        "Статус",
        "Ошибка",
        "Дата выгрузки",
    ]
    if not data:
        data = []  # пустой отчёт — только шапка (аналог pd.DataFrame(columns=...))

    wb = rows_workbook(data, "Отчет миграции", columns=df_columns)
    ws = wb["Отчет миграции"]
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["D"].width = 25

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        output,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": safe_disposition(filename)},
    )
