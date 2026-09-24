"""
Роутер экспорта: выгрузка файлов для ЛК площадок, предпросмотр, валидация, шаблоны.

Rate-limits (на идентификатор: user_id или IP):
  - /export/preview/{platform}    : 30/min          (лёгкий предпросмотр)
  - /export/template/{platform}   : 10/min          (шаблоны)
  - /export/platform/{platform}   : 10/min, 100/day (генерация XLSX)
  - /export/report                : 5/min, 50/day   (отчёт по всем товарам)
"""
import io
import logging
import time
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.responses import Response
from database.session import SessionLocal
from database.models import User, Product, PlatformCategorySpec
from services.xlsx_generator import generate_export
from core.auth import get_current_user
from core.platforms import Platform
from core.rate_limit import limiter
from database.repository import repo, op_log, stats_repo
from services.export_builder import build_upload_file, build_rows
from services.export_validator import validate_products, validate_product, has_errors

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


# ==================== ПРЕДПРОСМОТР ВЫГРУЗКИ ====================
@limiter.limit("30/minute")
@router.get("/export/preview/{platform}")
def export_preview(
    request: Request,                                   # ← добавлен для slowapi
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
    request: Request,                                   # ← добавлен для slowapi
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


# ==================== ФАЙЛ ДЛЯ ЛК ПЛОЩАДКИ (старый путь) ====================
@limiter.limit("10/minute;100/day")
@router.get("/export/platform/{platform}")
def export_for_platform(
    request: Request,                                   # ← добавлен для slowapi
    platform: str,
    status: str = "success",
    current_user: User = Depends(get_current_user),
):
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


# ==================== ВАЛИДАЦИЯ ПО СПЕКАМ (перед экспортом) ====================
@router.get("/export/validate/{platform}")
def validate_export(
    platform: str,
    current_user: User = Depends(get_current_user),
):
    """
    Проверка готовности товаров к экспорту по спекам площадки.
    Возвращает детальный список проблем с severity: error (блокирует) / warning.

    Дополнительно возвращает `missing_specs` — список категорий, для которых
    нет спека (т.е. маппинг указывает на «широкую» категорию вместо «Родитель / Тип»).
    """
    db = SessionLocal()
    try:
        query = db.query(Product).filter(Product.user_id == current_user.id)
        products = query.all()

        if not products:
            return {"total": 0, "errors": 0, "warnings": 0, "issues": [], "missing_specs": []}

        # Конвертируем товары в dict
        product_dicts = []
        for p in products:
            product_dicts.append({
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "external_id": p.external_id,
                "price": p.price,
                "category": p.category,
                "mapped_category": p.mapped_category,
                "barcode": p.barcode,
                "vat_rate": p.vat_rate,
                "package_weight_grams": p.package_weight_grams,
                "package_width_mm": p.package_width_mm,
                "package_height_mm": p.package_height_mm,
                "package_length_mm": p.package_length_mm,
                "okpd_code": p.okpd_code,
                "photos": p.photos or [],
                "attributes": [
                    {"name": a.name, "value": a.value} for a in (p.attributes or [])
                ],
            })

        # ✅ Подгружаем ГЛОБАЛЬНЫЕ спеки для всех категорий товаров (без user_id)
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

        # ✅ Категории без спека — критично для Ozon
        missing_specs = sorted(cat for cat in categories if cat not in specs_by_name)
        specs_by_category = {cat: specs_by_name.get(cat) for cat in categories}

        # Валидация по спекам
        from services.spec_validator import validate_products_by_specs
        result = validate_products_by_specs(product_dicts, specs_by_category, platform)

        # Добавляем информацию об отсутствии спеков
        result["missing_specs"] = missing_specs
        if missing_specs and platform == "ozon":
            result.setdefault("issues", []).append({
                "product_id": None,
                "product_name": "Система",
                "category": "—",
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
            # Пересчёт счётчиков
            result["errors"] = result.get("errors", 0) + 1

        return result
    finally:
        db.close()


# ==================== ОТЧЁТ ПО ВСЕМ ТОВАРАМ ====================
@limiter.limit("5/minute;50/day")
@router.get("/export/report")
def export_migration_report(
    request: Request,                                   # ← добавлен для slowapi
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
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==================== XLSX v2 ПОД РЕАЛЬНЫЙ ШАБЛОН OZON ====================
@router.get("/export/xlsx/{platform}")
def export_xlsx_v2(
    platform: str,
    status: str = "success",
    current_user: User = Depends(get_current_user),
):
    """
    XLSX v2: файл, СТРУКТТУРНО идентичный реальному шаблону площадки.
    ✅ Глобальные спеки (без user_id)
    ✅ Отсев товаров с error-issues (иначе Ozon отклонит)
    ✅ Громкая ошибка если спека нет для категории (иначе файл без атрибутов)
    """
    # Защита от пустого/невалидного status
    if not status or status not in ("success", "pending", "processing", "error", "all"):
        status = "success"

    db = SessionLocal()
    try:
        query = db.query(Product).filter(Product.user_id == current_user.id)
        if status != "all":
            query = query.filter(Product.status == status)
        products = query.all()

        if not products:
            raise HTTPException(
                status_code=400,
                detail=f"Нет товаров со статусом '{status}'. "
                       f"Импортируйте товары и выполните миграцию (кнопка «Мигрировать») перед выгрузкой.",
            )

        product_dicts = []
        for p in products:
            product_dicts.append({
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "external_id": p.external_id,
                "price": p.price,
                "category": p.category,
                "mapped_category": p.mapped_category,
                "barcode": p.barcode,
                "vat_rate": p.vat_rate,
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
            })

        categories = {
            (p["mapped_category"] or p["category"] or "Без категории") for p in product_dicts
        }

        # ✅ ГЛОБАЛЬНЫЕ спеки — без user_id (одна строка на категорию для всех пользователей)
        specs = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == platform,
                PlatformCategorySpec.category_name.in_(categories),
            )
            .all()
        )
        specs_by_name = {s.category_name: s.spec for s in specs}

        # ✅ Громкая ошибка если для какой-то категории нет спека
        no_spec_categories = sorted(cat for cat in categories if cat not in specs_by_name)
        if no_spec_categories and platform == "ozon":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Для {len(no_spec_categories)} категорий нет спека Ozon: "
                    f"{', '.join(no_spec_categories[:5])}{'…' if len(no_spec_categories) > 5 else ''}. "
                    f"В маппинге выберите точную категорию Ozon в формате «Родитель / Тип» "
                    f"(например, «Одежда / Футболка»). Список всех категорий — на странице «Спецификации»."
                ),
            )

        specs_by_category = {cat: specs_by_name.get(cat) for cat in categories}

        # ✅ Валидация + отсев невалидных товаров перед генерацией
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
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ни один товар не прошёл валидацию ({len(bad_ids)} с ошибками). "
                    f"Проверьте цены, ТН ВЭД, габариты, обязательные атрибуты. "
                    f"Подробности — в блоке валидации на странице экспорта."
                ),
            )

        # Генерация
        data, filename = generate_export(exportable, specs_by_category, platform)

        # Логирование успешного экспорта
        op_log.log_file_operation(
            user_id=current_user.id, operation="export", platform=platform,
            filename=filename, status="success",
            total_rows=len(product_dicts), imported=len(exportable),
            updated=0, failed=len(bad_ids),
            errors=[{"product_id": i, "error": "исключён: ошибки валидации"} for i in list(bad_ids)[:10]],
        )

        t0 = time.perf_counter()
        stats_repo.record(
            user_id=current_user.id, operation="export", platform=platform,
            status="success", total_items=len(exportable),
            success_items=len(exportable), failed_items=len(bad_ids),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )

        media = ("application/zip" if filename.endswith(".zip")
                 else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        return Response(
            content=data,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        db.close()