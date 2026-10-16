"""
Роутер экспорта: выгрузка файлов для ЛК площадок, предпросмотр, валидация, шаблоны.

✅ v6:
  - Поддержка параметра platform в эндпоинтах загрузки/скачивания/удаления эталонов
    (теперь можно загружать оригинальные шаблоны Яндекс Маркета, WB и Ozon).
  - Поддержка фильтрации по списку product_ids во всех эндпоинтах экспорта.
"""

import io
import logging
import re as _re
import time
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from core.auth import get_current_user
from core.platforms import Platform
from core.rate_limit import limiter
from database.models import PlatformCategorySpec, Product, User
from database.repository import op_log, repo, stats_repo
from database.session import SessionLocal
from services import template_filler
from services.export_builder import build_rows, build_upload_file
from services.export_validator import has_errors, validate_product, validate_products
from services.xlsx_generator import generate_export

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Export"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _safe_disposition(filename: str) -> str:
    ascii_name = "".join(c if ord(c) < 128 else "_" for c in filename).strip("_") or "export.xlsx"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def _parse_product_ids(product_id: int | None, product_ids: str | None) -> list[int]:
    ids: list[int] = []
    if product_id is not None and product_id > 0:
        ids.append(int(product_id))
    if product_ids:
        for part in str(product_ids).split(","):
            part = part.strip()
            if part.isdigit() and int(part) > 0:
                val = int(part)
                if val not in ids:
                    ids.append(val)
    return ids


def _normalize_category_name(name: str, platform: str = "ozon") -> str:
    raw = (name or "").strip()
    if not raw or raw.lower() in ("универсальный", "общий", "все категории", "default", "all"):
        return "Универсальный (все категории)"
    parts = [p.strip() for p in _re.split(r"[>/\\]", raw) if p.strip()]
    candidate = " / ".join(parts[-2:]) if len(parts) >= 2 else raw

    db = SessionLocal()
    try:
        row = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == platform,
                PlatformCategorySpec.category_name == candidate,
            )
            .first()
        )
        return row.category_name if row else candidate
    finally:
        db.close()


def _get_products_for_export(
    current_user: User, status: str, selected_ids: list[int] | None = None
) -> list:
    is_admin = current_user.role == "admin"
    result = repo.get_all(user_id=current_user.id, is_admin=is_admin, limit=10000)
    products = result["products"]
    if selected_ids:
        wanted = set(selected_ids)
        return [p for p in products if p["id"] in wanted]
    if status != "all":
        products = [p for p in products if p["status"] == status]
    return products


# ==================== ЭТАЛОННЫЕ ШАБЛОНЫ (Мультиплатформенные) ====================


@router.post("/export/ozon-template/upload")
async def upload_official_template(
    request: Request,
    category_name: str = Form("Универсальный (все категории)"),
    platform: str = Form("ozon"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Приём эталонного XLSX-шаблона для любой площадки (Ozon, Яндекс Маркет, WB, Магнит)."""
    pl = (platform or "ozon").lower().strip()
    cat = _normalize_category_name(category_name, pl)

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Нужен файл .xlsx — шаблон из кабинета площадки")

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
def list_official_templates(platform: str = Query("ozon"), current_user: User = Depends(get_current_user)):
    return {"templates": template_filler.list_template_names(platform=platform)}


@router.get("/export/ozon-template/meta")
def list_official_templates_meta(current_user: User = Depends(get_current_user)):
    return {"templates": template_filler.list_official_templates()}


@router.get("/export/ozon-template/status")
def ozon_template_status(
    category_name: str = "Универсальный (все категории)",
    platform: str = Query("ozon"),
    current_user: User = Depends(get_current_user),
):
    pl = (platform or "ozon").lower().strip()
    cat = _normalize_category_name(category_name, pl)
    meta = template_filler.get_template_meta(cat, platform=pl)
    return {
        "platform": pl,
        "category": cat,
        "has_official_template": meta is not None,
        "meta": meta,
    }


@router.get("/export/ozon-template/download")
def download_official_template(
    category_name: str = "Универсальный (все категории)",
    platform: str = Query("ozon"),
    current_user: User = Depends(get_current_user),
):
    pl = (platform or "ozon").lower().strip()
    cat = _normalize_category_name(category_name, pl)
    data = template_filler.read_template_bytes(cat, platform=pl)
    if not data:
        raise HTTPException(status_code=404, detail=f"Эталон для «{cat}» [{pl}] не найден")
    fname = f"{pl}_{cat.replace('/', '_').strip()}.xlsx"
    return Response(
        content=data,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": _safe_disposition(fname)},
    )


@router.delete("/export/ozon-template")
def delete_official_template(
    category_name: str = "Универсальный (все категории)",
    platform: str = Query("ozon"),
    current_user: User = Depends(get_current_user),
):
    pl = (platform or "ozon").lower().strip()
    cat = _normalize_category_name(category_name, pl)
    deleted = template_filler.delete_official_template(cat, platform=pl)
    if not deleted:
        raise HTTPException(status_code=404, detail="Эталон не найден")
    logger.info(f"🗑 Эталон [{pl}] удалён: '{cat}' (пользователь {current_user.username})")
    return {"ok": True, "platform": pl, "category": cat}


# ==================== ПРЕДПРОСМОТР ВЫГРУЗКИ ====================


@limiter.limit("30/minute")
@router.get("/export/preview/{platform}")
def export_preview(
    request: Request,
    platform: str,
    status: str = "success",
    product_id: int = Query(None),
    product_ids: str = Query(None),
    current_user: User = Depends(get_current_user),
):
    if platform not in Platform.all_values():
        raise HTTPException(status_code=404, detail=f"Платформа '{platform}' не найдена")

    ids = _parse_product_ids(product_id, product_ids)
    products = _get_products_for_export(current_user, status, selected_ids=ids)
    if not products:
        return {
            "success": True,
            "columns": [],
            "rows": [],
            "validation": {
                "total": 0,
                "ready": 0,
                "with_warnings": 0,
                "with_errors": 0,
                "issues": [],
            },
        }

    validation = validate_products(products, platform)
    rows = build_rows(products[:10], platform)
    columns = list(rows[0].keys()) if rows else []

    return {"success": True, "columns": columns, "rows": rows, "validation": validation}


# ==================== ШАБЛОН ВЫГРУЗКИ ====================


@limiter.limit("10/minute")
@router.get("/export/template/{platform}")
def export_template(
    request: Request,
    platform: str,
    current_user: User = Depends(get_current_user),
):
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

        instructions = pd.DataFrame(
            {
                "Инструкция": [
                    f"Шаблон выгрузки для {platform}",
                    "1. Заполняйте по одной строке на товар.",
                    "2. Не меняйте заголовки колонок и имена листов.",
                    "3. Фото указывайте прямыми ссылками через '; '.",
                    "4. Готовый файл загрузите в личном кабинете площадки.",
                ]
            }
        )
        instructions.to_excel(writer, index=False, sheet_name="Инструкция")
        writer.sheets["Инструкция"].column_dimensions["A"].width = 80

    output.seek(0)
    filename = f"template_{platform}.xlsx"
    return StreamingResponse(
        output,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": _safe_disposition(filename)},
    )


# ==================== ФАЙЛ ДЛЯ ЛК ПЛОЩАДКИ ====================


@limiter.limit("10/minute;100/day")
@router.get("/export/platform/{platform}")
def export_for_platform(
    request: Request,
    platform: str,
    status: str = "success",
    product_id: int = Query(None),
    product_ids: str = Query(None),
    current_user: User = Depends(get_current_user),
):
    if platform not in Platform.all_values():
        raise HTTPException(status_code=404, detail=f"Платформа '{platform}' не найдена")

    ids = _parse_product_ids(product_id, product_ids)
    products = _get_products_for_export(current_user, status, selected_ids=ids)

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
        output = build_upload_file(valid_products, platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    return StreamingResponse(
        output,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": _safe_disposition(filename)},
    )


# ==================== ВАЛИДАЦИЯ ПО СПЕКАМ ====================


@router.get("/export/validate/{platform}")
def validate_export(
    platform: str,
    status: str = "all",
    product_id: int = Query(None),
    product_ids: str = Query(None),
    current_user: User = Depends(get_current_user),
):
    ids = _parse_product_ids(product_id, product_ids)
    db = SessionLocal()
    try:
        query = db.query(Product).filter(Product.user_id == current_user.id)
        if ids:
            query = query.filter(Product.id.in_(ids))
        elif status and status != "all":
            query = query.filter(Product.status == status)
        products = query.all()

        if not products:
            return {"total": 0, "errors": 0, "warnings": 0, "issues": [], "missing_specs": []}

        product_dicts = []
        for p in products:
            product_dicts.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "sku": p.sku,
                    "external_id": p.external_id,
                    "price": p.price,
                    "brand": p.brand,
                    "description": p.description,
                    "category": p.category,
                    "mapped_category": p.mapped_category,
                    "barcode": p.barcode,
                    "vat_rate": p.vat_rate,
                    "weight_grams": p.weight_grams,
                    "package_weight_grams": p.package_weight_grams,
                    "package_width_mm": p.package_width_mm,
                    "package_height_mm": p.package_height_mm,
                    "package_length_mm": p.package_length_mm,
                    "okpd_code": p.okpd_code,
                    "photos": p.photos or [],
                    "attributes": [
                        {"name": a.name, "value": a.value} for a in (p.attributes or [])
                    ],
                }
            )

        categories = {
            (p["mapped_category"] or p["category"] or "Без категории") for p in product_dicts
        }
        specs = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == platform,
                PlatformCategorySpec.category_name.in_(categories),
            )
            .all()
        )
        specs_by_name = {s.category_name: s.spec for s in specs}

        missing_specs = sorted(cat for cat in categories if cat not in specs_by_name)
        specs_by_category = {cat: specs_by_name.get(cat) for cat in categories}

        from services.spec_validator import validate_products_by_specs

        result = validate_products_by_specs(product_dicts, specs_by_category, platform)
        result["missing_specs"] = missing_specs
        return result
    finally:
        db.close()


# ==================== ОТЧЁТ ПО ВСЕМ ТОВАРАМ ====================


@limiter.limit("5/minute;50/day")
@router.get("/export/report")
def export_migration_report(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    is_admin = current_user.role == "admin"
    result = repo.get_all(user_id=current_user.id, is_admin=is_admin, limit=10000)
    products = result["products"]

    data = []
    for p in products:
        data.append(
            {
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
            }
        )

    df = pd.DataFrame(data)
    if df.empty:
        df = pd.DataFrame(
            columns=[
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
        )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Отчет миграции")
        ws = writer.sheets["Отчет миграции"]
        ws.column_dimensions["B"].width = 40
        ws.column_dimensions["D"].width = 25

    output.seek(0)
    filename = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        output,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": _safe_disposition(filename)},
    )


# ==================== XLSX v2 (Экспорт по шаблону эталона) ====================


@limiter.limit("30/minute")
@router.get("/export/xlsx/{platform}")
def export_xlsx_v2(
    request: Request,
    platform: str,
    status: str = "success",
    product_id: int = Query(None),
    product_ids: str = Query(None),
    current_user: User = Depends(get_current_user),
):
    """
    XLSX v2: выгрузка по эталонному шаблону площадки (Ozon, Яндекс Маркет, WB, Магнит).
    Если загружен эталон — заполняется оригинальный файл площадки (1:1).
    """
    if not status or status not in ("success", "pending", "processing", "error", "all"):
        status = "success"

    ids = _parse_product_ids(product_id, product_ids)

    db = SessionLocal()
    try:
        query = db.query(Product).filter(Product.user_id == current_user.id)
        if ids:
            query = query.filter(Product.id.in_(ids))
            logger.info(f"📥 Экспорт выбранных товаров: ids={ids}, platform={platform}")
        elif status != "all":
            query = query.filter(Product.status == status)
        products = query.all()

        if not products:
            detail = (
                f"Выбранные товары ({ids}) не найдены"
                if ids
                else f"Нет товаров со статусом '{status}'. Импортируйте товары и выполните миграцию."
            )
            raise HTTPException(status_code=400, detail=detail)

        product_dicts = []
        for p in products:
            product_dicts.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "sku": p.sku,
                    "external_id": p.external_id,
                    "price": p.price,
                    "brand": p.brand,
                    "description": p.description,
                    "category": p.category,
                    "mapped_category": p.mapped_category,
                    "barcode": p.barcode,
                    "vat_rate": p.vat_rate,
                    "weight_grams": p.weight_grams,
                    "package_weight_grams": p.package_weight_grams,
                    "package_width_mm": p.package_width_mm,
                    "package_height_mm": p.package_height_mm,
                    "package_length_mm": p.package_length_mm,
                    "okpd_code": p.okpd_code,
                    "units_per_item": p.units_per_item,
                    "photos": p.photos or [],
                    "attributes": [
                        {"name": a.name, "value": a.value} for a in (p.attributes or [])
                    ],
                    "variants": [
                        {"sku": v.sku, "size": v.size, "color": v.color, "price": v.price}
                        for v in (p.variants or [])
                    ],
                }
            )

        categories = {
            (p["mapped_category"] or p["category"] or "Без категории") for p in product_dicts
        }
        specs = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == platform,
                PlatformCategorySpec.category_name.in_(categories),
            )
            .all()
        )
        specs_by_name = {s.category_name: s.spec for s in specs}
        specs_by_category = {cat: specs_by_name.get(cat) for cat in categories}

        data, filename = generate_export(product_dicts, specs_by_category, platform)

        t0 = time.perf_counter()
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
        return Response(
            content=data,
            media_type=media,
            headers={"Content-Disposition": _safe_disposition(filename)},
        )
    finally:
        db.close()