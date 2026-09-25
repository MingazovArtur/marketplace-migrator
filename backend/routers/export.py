"""
Роутер экспорта: выгрузка файлов для ЛК площадок, предпросмотр, валидация, шаблоны.

✅ v3: добавлено хранилище ЭТАЛОННЫХ шаблонов Ozon (файлы, скачанные пользователем
в кабинете селлера): upload / list / status / delete. При выгрузке XLSX v2 эталон
используется как каркас — формат совпадает с площадкой на 100%.

Rate-limits:
  - /export/preview/{platform}    : 30/min
  - /export/template/{platform}   : 10/min
  - /export/platform/{platform}   : 10/min, 100/day
  - /export/report                : 5/min, 50/day
  - /export/xlsx/{platform}       : 30/min
"""
import io
import logging
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
    """Безопасный Content-Disposition для имён с кириллицей (RFC 5987)."""
    ascii_name = "".join(c if ord(c) < 128 else "_" for c in filename).strip("_") or "export.xlsx"
    encoded = quote(filename, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'


def _get_products_for_export(current_user: User, status: str) -> list:
    is_admin = current_user.role == "admin"
    result = repo.get_all(user_id=current_user.id, is_admin=is_admin, limit=10000)
    products = result["products"]
    if status != "all":
        products = [p for p in products if p["status"] == status]
    return products


# ==================== ЭТАЛОННЫЕ ШАБЛОНЫ OZON (файлы пользователя) ====================

@router.post("/export/ozon-template/upload")
async def upload_official_template(
    request: Request,
    category_name: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Приём эталонного XLSX-шаблона, скачанного в кабинете Ozon для категории.
    Файл проверяется на похожесть структуры и сохраняется как каркас для выгрузки.
    """
    category_name = (category_name or "").strip()
    if not category_name:
        raise HTTPException(status_code=400, detail="Укажите категорию (формат «Родитель / Тип»)")
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Нужен файл .xlsx — шаблон из кабинета Ozon")

    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл больше 15 МБ")

    problem = template_filler.validate_template_bytes(data)
    if problem:
        raise HTTPException(status_code=400, detail=f"Это не шаблон Ozon: {problem}")

    template_filler.save_official_template(category_name, data)
    return {
        "ok": True,
        "category": category_name,
        "size": len(data),
        "message": f"Эталон для «{category_name}» сохранён. Выгрузка будет собрана на его основе.",
    }


@router.get("/export/ozon-template/list")
def list_official_templates(current_user: User = Depends(get_current_user)):
    """Список категорий, для которых загружен эталонный шаблон."""
    return {"templates": template_filler.list_official_templates()}


@router.get("/export/ozon-template/status")
def ozon_template_status(
    category_name: str,
    current_user: User = Depends(get_current_user),
):
    return {
        "category": category_name,
        "has_official_template": template_filler.has_official_template(category_name),
    }


@router.delete("/export/ozon-template")
def delete_official_template(
    category_name: str,
    current_user: User = Depends(get_current_user),
):
    deleted = template_filler.delete_official_template(category_name.strip())
    if not deleted:
        raise HTTPException(status_code=404, detail="Эталон для этой категории не найден")
    return {"ok": True, "category": category_name}


# ==================== ПРЕДПРОСМОТР ВЫГРУЗКИ ====================

@limiter.limit("30/minute")
@router.get("/export/preview/{platform}")
def export_preview(
    request: Request,
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


# ==================== ШАБЛОН ВЫГРУЗКИ ====================

@limiter.limit("10/minute")
@router.get("/export/template/{platform}")
def export_template(
    request: Request,
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
        headers={"Content-Disposition": _safe_disposition(filename)},
    )


# ==================== ФАЙЛ ДЛЯ ЛК ПЛОЩАДКИ (старый путь) ====================

@limiter.limit("10/minute;100/day")
@router.get("/export/platform/{platform}")
def export_for_platform(
    request: Request,
    platform: str,
    status: str = "success",
    current_user: User = Depends(get_current_user),
):
    """Файл XLSX для загрузки в ЛК площадки. Товары с ошибками валидации исключаются."""
    if platform not in Platform.all_values():
        raise HTTPException(status_code=404, detail=f"Платформа '{platform}' не найдена")

    products = _get_products_for_export(current_user, status)

    valid_products, skipped = [], []
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
        user_id=current_user.id, operation="export", platform=platform,
        status="success", total_items=len(valid_products),
        success_items=len(valid_products),
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
    return StreamingResponse(
        output, media_type=XLSX_MIME,
        headers={"Content-Disposition": _safe_disposition(filename)},
    )


# ==================== ВАЛИДАЦИЯ ПО СПЕКАМ ====================

@router.get("/export/validate/{platform}")
def validate_export(
    platform: str,
    status: str = "all",
    product_id: int = Query(None, description="Фильтр по одному товару (для модалки миграции)"),
    current_user: User = Depends(get_current_user),
):
    """Проверка готовности товаров к экспорту по спекам площадки."""
    db = SessionLocal()
    try:
        query = db.query(Product).filter(Product.user_id == current_user.id)
        if product_id:
            query = query.filter(Product.id == product_id)
        elif status and status != "all":
            query = query.filter(Product.status == status)
        products = query.all()

        if not products:
            return {"total": 0, "errors": 0, "warnings": 0, "issues": [], "missing_specs": []}

        product_dicts = []
        for p in products:
            product_dicts.append({
                "id": p.id, "name": p.name, "sku": p.sku, "external_id": p.external_id,
                "price": p.price, "category": p.category, "mapped_category": p.mapped_category,
                "barcode": p.barcode, "vat_rate": p.vat_rate,
                "package_weight_grams": p.package_weight_grams,
                "package_width_mm": p.package_width_mm,
                "package_height_mm": p.package_height_mm,
                "package_length_mm": p.package_length_mm,
                "okpd_code": p.okpd_code, "photos": p.photos or [],
                "attributes": [{"name": a.name, "value": a.value} for a in (p.attributes or [])],
            })

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
        if missing_specs and platform == "ozon":
            result.setdefault("issues", []).append({
                "product_id": None, "product_name": "Система", "category": "—",
                "issues": [{
                    "field": "spec",
                    "message": (
                        f"Нет спека Ozon для {len(missing_specs)} категорий: "
                        f"{', '.join(missing_specs[:5])}{'…' if len(missing_specs) > 5 else ''}. "
                        f"В маппинге выберите точную категорию в формате «Родитель / Тип» "
                        f"(список — на странице «Спецификации»)."
                    ),
                    "severity": "error",
                }],
            })
            result["errors"] = result.get("errors", 0) + 1

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
        headers={"Content-Disposition": _safe_disposition(filename)},
    )


# ==================== XLSX v2 ПОД РЕАЛЬНЫЙ ШАБЛОН OZON ====================

@limiter.limit("30/minute")
@router.get("/export/xlsx/{platform}")
def export_xlsx_v2(
    request: Request,
    platform: str,
    status: str = "success",
    product_id: int = Query(None, description="ID одного товара (авто-экспорт из модалки миграции)"),
    current_user: User = Depends(get_current_user),
):
    """
    XLSX v2: файл под реальный шаблон площадки.
    ✅ Если для категории загружен ЭТАЛОННЫЙ шаблон Ozon — файл собирается НА НЁМ
       (формат 1:1, кабинет распознаёт всегда).
    ✅ Иначе — генерация из спека категории (fallback).
    ✅ Отсев товаров с error-issues; громкая ошибка при отсутствии спека.
    """
    if not status or status not in ("success", "pending", "processing", "error", "all"):
        status = "success"

    db = SessionLocal()
    try:
        query = db.query(Product).filter(Product.user_id == current_user.id)
        if product_id:
            query = query.filter(Product.id == product_id)
            logger.info(f"📥 Экспорт одного товара: product_id={product_id}, platform={platform}")
        elif status != "all":
            query = query.filter(Product.status == status)
        products = query.all()

        if not products:
            detail = (
                f"Товар #{product_id} не найден" if product_id
                else f"Нет товаров со статусом '{status}'. Импортируйте товары и выполните "
                     f"миграцию (кнопка «Мигрировать») перед выгрузкой."
            )
            raise HTTPException(status_code=400, detail=detail)

        product_dicts = []
        for p in products:
            product_dicts.append({
                "id": p.id, "name": p.name, "sku": p.sku, "external_id": p.external_id,
                "price": p.price, "category": p.category, "mapped_category": p.mapped_category,
                "barcode": p.barcode, "vat_rate": p.vat_rate,
                "package_weight_grams": p.package_weight_grams,
                "package_width_mm": p.package_width_mm,
                "package_height_mm": p.package_height_mm,
                "package_length_mm": p.package_length_mm,
                "okpd_code": p.okpd_code, "units_per_item": p.units_per_item,
                "photos": p.photos or [],
                "attributes": [{"name": a.name, "value": a.value} for a in (p.attributes or [])],
            })

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

        no_spec_categories = sorted(cat for cat in categories if cat not in specs_by_name)
        if no_spec_categories and platform == "ozon":
            # ✅ Эталон заменяет спек: если шаблон загружен — спек не требуем
            without_template = [c for c in no_spec_categories
                                if not template_filler.has_official_template(c)]
            if without_template:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Для {len(without_template)} категорий нет спека Ozon: "
                        f"{', '.join(without_template[:5])}"
                        f"{'…' if len(without_template) > 5 else ''}. "
                        f"Загрузите эталонный шаблон категории в окне «Выгрузка» "
                        f"или выберите точную категорию в маппинге («Родитель / Тип»)."
                    ),
                )

        specs_by_category = {cat: specs_by_name.get(cat) for cat in categories}

        from services.spec_validator import validate_products_by_specs
        validation = validate_products_by_specs(product_dicts, specs_by_category, platform)
        bad_ids = {
            item["product_id"]
            for item in validation["issues"]
            if any(i["severity"] == "error" for i in item["issues"])
        }
        exportable = [p for p in product_dicts if p["id"] not in bad_ids]

        if bad_ids:
            logger.warning(
                f"⚠️ Исключено из XLSX v2: {len(bad_ids)} товаров с ошибками "
                f"(из {len(product_dicts)}): ids={list(bad_ids)[:10]}"
            )

        if not exportable:
            if product_id and validation.get("issues"):
                problems = []
                for item in validation["issues"]:
                    for i in item["issues"]:
                        if i["severity"] == "error":
                            problems.append(f"• {i['field']}: {i['message']}")
                detail = (
                    f"Товар #{product_id} не прошёл валидацию. Исправьте через UI "
                    f"(кнопки «Логистика», «Характеристики», «Фото»):\n" + "\n".join(problems[:10])
                )
            else:
                detail = (
                    f"Ни один товар не прошёл валидацию ({len(bad_ids)} с ошибками). "
                    f"Проверьте цены, ТН ВЭД, габариты, обязательные атрибуты. "
                    f"Подробности — в блоке валидации на странице экспорта."
                )
            raise HTTPException(status_code=400, detail=detail)

        # ✅ Генерация: эталон优先 (внутри generate_export), иначе спек
        data, filename = generate_export(exportable, specs_by_category, platform)

        used_templates = sorted(
            cat for cat in categories if template_filler.has_official_template(cat)
        )
        op_log.log_file_operation(
            user_id=current_user.id, operation="export", platform=platform,
            filename=filename, status="success",
            total_rows=len(product_dicts), imported=len(exportable),
            updated=0, failed=len(bad_ids),
            errors=[{"product_id": i, "error": "исключён: ошибки валидации"} for i in list(bad_ids)[:10]],
        )
        if used_templates:
            logger.info(f"🧾 Выгрузка собрана на эталонных шаблонах: {used_templates}")

        t0 = time.perf_counter()
        stats_repo.record(
            user_id=current_user.id, operation="export", platform=platform,
            status="success", total_items=len(exportable),
            success_items=len(exportable), failed_items=len(bad_ids),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

        media = ("application/zip" if filename.endswith(".zip") else XLSX_MIME)
        return Response(
            content=data,
            media_type=media,
            headers={"Content-Disposition": _safe_disposition(filename)},
        )
    finally:
        db.close()