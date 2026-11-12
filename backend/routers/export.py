"""
Роутер экспорта: выгрузка файлов для ЛК площадок, предпросмотр, валидация, шаблоны.

✅ v8 (AsyncSession + asyncpg + Celery Queue `xlsx_export`):
  - Все обращения к БД переведены на неблокирующий AsyncSession (get_async_db).
  - Связанные коллекции (Product.attributes, Product.variants) загружаются
    одним циклом через selectinload() без ошибок MissingGreenlet.
  - Вынос тяжёлой генерации openpyxl в выделенную очередь Celery `xlsx_export`
    (прозрачный offload в GET /export/xlsx/{platform} + task-эндпоинты).
  - Поддержка параметра platform в эндпоинтах загрузки/скачивания/удаления эталонов
    (Яндекс Маркет, Ozon, Wildberries, Магнит).
  - Поддержка фильтрации по списку product_ids во всех эндпоинтах экспорта.
"""

import asyncio
import io
import logging
import os
import re as _re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from celery_app import celery_app
from core.auth import get_current_admin_user, get_current_user
from core.config import settings
from core.platforms import Platform
from core.rate_limit import limiter
from database.models import PlatformCategorySpec, Product, User
from database.repository import op_log, stats_repo
from database.session import get_async_db
from services import template_filler
from services.export_builder import build_rows, build_upload_file
from services.export_validator import has_errors, validate_product, validate_products
from services.xlsx_generator import generate_export
from services.xlsx_io import rows_workbook, write_columns
from tasks import generate_xlsx_export_task, get_progress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Export"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Порог количества товаров, начиная с которого сборка XLSX автоматически уходит в очередь xlsx_export
CELERY_XLSX_THRESHOLD = int(os.getenv("CELERY_XLSX_THRESHOLD", "30"))
CELERY_XLSX_TIMEOUT_SEC = int(os.getenv("CELERY_XLSX_TIMEOUT_SEC", "180"))

# --- IDOR-защита фоновых задач экспорта (было В-2 код-ревью) ---
# Реестр владельцев task_id: без него любой авторизованный пользователь
# мог скачать чужой XLSX/ZIP, зная/подобрав task_id.
_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
EXPORT_TASK_TTL_SEC = 24 * 3600  # ключ живёт столько же, сколько файл в /media/exports


def _register_export_task_owner(task_id: str, user_id: int) -> None:
    """Привязка задачи к владельцу (вызывается сразу после apply_async)."""
    try:
        _redis.setex(f"export_task_owner:{task_id}", EXPORT_TASK_TTL_SEC, str(user_id))
    except Exception as e:
        # Не критично: fallback-проверка по user_id в результате задачи
        logger.warning(f"Не удалось записать владельца задачи {task_id}: {e}")


def _assert_export_task_owner(task_id: str, current_user: User) -> None:
    """
    Задача экспорта должна принадлежать current_user (админ — исключение).
    Чужая задача выглядит как несуществующая (404, без раскрытия факта).
    """
    if getattr(current_user, "role", None) == "admin":
        return

    owner = None
    try:
        owner = _redis.get(f"export_task_owner:{task_id}")
    except Exception as e:
        logger.warning(f"Redis недоступен при проверке владельца задачи {task_id}: {e}")

    if owner is not None:
        if str(owner) == str(current_user.id):
            return
        raise HTTPException(status_code=404, detail="Задача не найдена")

    # Ключа нет (Redis чистился или задача создана до этого патча):
    # для завершённых задач проверяем user_id, который воркер кладёт в результат.
    res = celery_app.AsyncResult(task_id)
    if res.ready() and res.successful() and isinstance(res.result, dict):
        owner_id = res.result.get("user_id")
        if owner_id is not None and str(owner_id) == str(current_user.id):
            return

    raise HTTPException(status_code=404, detail="Задача не найдена")


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


async def _normalize_category_name(
    db: AsyncSession, name: str, platform: str = "ozon"
) -> str:
    raw = (name or "").strip()
    if not raw or raw.lower() in ("универсальный", "общий", "все категории", "default", "all"):
        return "Универсальный (все категории)"
    parts = [p.strip() for p in _re.split(r"[>/\\]", raw) if p.strip()]
    candidate = " / ".join(parts[-2:]) if len(parts) >= 2 else raw

    stmt = select(PlatformCategorySpec).where(
        PlatformCategorySpec.platform == platform,
        PlatformCategorySpec.category_name == candidate,
    )
    res = await db.execute(stmt)
    row = res.scalars().first()
    return row.category_name if row else candidate


def _product_to_dict(p: Product) -> dict:
    """Преобразует ORM-модель Product (с предзагруженными attributes и variants) в словарь."""
    return {
        "id": p.id,
        "user_id": getattr(p, "user_id", None),
        "name": p.name,
        "sku": p.sku,
        "external_id": p.external_id,
        "price": p.price,
        "source": getattr(p, "source", ""),
        "status": getattr(p, "status", ""),
        "error_message": getattr(p, "error_message", None),
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
        "units_per_item": getattr(p, "units_per_item", 1),
        "stock": getattr(p, "stock", 0),
        "photos": p.photos or [],
        "attributes": [
            {"name": a.name, "value": a.value} for a in (p.attributes or [])
        ],
        "variants": [
            {"sku": v.sku, "size": v.size, "color": v.color, "price": v.price}
            for v in (p.variants or [])
        ],
        # ✅ v4: для инкрементального экспорта (сводка «новые/изменённые»)
        "last_export_at": getattr(p, "last_export_at", None),
        "last_export_platform": getattr(p, "last_export_platform", None),
        "updated_at": getattr(p, "updated_at", None),
    }


async def _get_products_for_export_async(
    db: AsyncSession,
    current_user: User,
    status: str,
    selected_ids: list[int] | None = None,
    limit: int = 10000,
    changed_since: bool = False,
) -> list[dict]:
    """Асинхронная выборка товаров для экспорта с неблокирующей подгрузкой атрибутов и вариаций.

    ✅ v4: changed_since=True — только «инкремент»: товары, изменившиеся после
    последней выгрузки (updated_at > last_export_at) или ещё не выгружавшиеся.
    """
    is_admin = getattr(current_user, "role", "") == "admin"
    stmt = (
        select(Product)
        .options(
            selectinload(Product.attributes),
            selectinload(Product.variants),
        )
        .order_by(Product.id.desc())
        .limit(limit)
    )
    if not is_admin:
        stmt = stmt.where(Product.user_id == current_user.id)

    if selected_ids:
        stmt = stmt.where(Product.id.in_(selected_ids))
    elif status and status != "all":
        stmt = stmt.where(Product.status == status)

    if changed_since:
        stmt = stmt.where(
            (Product.last_export_at.is_(None))
            | (Product.updated_at > Product.last_export_at)
        )

    res = await db.execute(stmt)
    products = res.scalars().all()
    return [_product_to_dict(p) for p in products]


async def _incremental_stats(products: list) -> dict:
    """✅ v4: сводка для фильтра «только изменённые»: новые/изменённые/без изменений.

    Принимает ORM-объекты или словари _product_to_dict (в словаре поля
    last_export_at/updated_at добавлены v4).
    """
    def _get(p, key):
        return p.get(key) if isinstance(p, dict) else getattr(p, key, None)

    new = changed = unchanged = 0
    for p in products:
        last_exp = _get(p, "last_export_at")
        updated = _get(p, "updated_at")
        if last_exp is None:
            new += 1
        elif updated and updated > last_exp:
            changed += 1
        else:
            unchanged += 1
    return {"new": new, "changed": changed, "unchanged": unchanged}


async def _mark_exported(db: AsyncSession, product_ids: list[int], platform: str) -> None:
    """✅ v4: зафиксировать факт выгрузки (для последующих инкрементальных экспортов).

    Не бросает исключений: пометка — вспомогательная операция, файл уже отдан.
    """
    if not product_ids:
        return
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        res = await db.execute(
            update(Product)
            .where(Product.id.in_(product_ids))
            .values(last_export_at=now, last_export_platform=platform)
        )
        await db.commit()
        logger.info(f"📤 mark_exported: {res.rowcount} товаров помечены выгруженными на {platform}")
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.warning(f"Не удалось пометить товары выгруженными: {e}")


async def _load_specs_by_category_async(
    db: AsyncSession, product_dicts: list[dict], platform: str
) -> dict[str, dict | None]:
    categories = {
        (p["mapped_category"] or p["category"] or "Без категории") for p in product_dicts
    }
    spec_stmt = select(PlatformCategorySpec).where(
        PlatformCategorySpec.platform == platform,
        PlatformCategorySpec.category_name.in_(categories),
    )
    spec_res = await db.execute(spec_stmt)
    specs = spec_res.scalars().all()
    specs_by_name = {s.category_name: s.spec for s in specs}
    return {cat: specs_by_name.get(cat) for cat in categories}


async def _run_xlsx_via_celery_or_thread(
    product_dicts: list[dict],
    specs_by_category: dict,
    platform: str,
    user_id: int,
    force_celery: bool = False,
) -> tuple[bytes, str]:
    """
    Выполняет генерацию XLSX:
      - Если товаров >= CELERY_XLSX_THRESHOLD (или force_celery=True), отправляет задачу
        в изолированную очередь `xlsx_export` и неблокирующе ждёт файл.
      - Для малых партий (или при недоступности воркера) выполняет генерацию в отдельном
        потоке через asyncio.to_thread, не блокируя event loop FastAPI.
    """
    use_celery = force_celery or len(product_dicts) >= CELERY_XLSX_THRESHOLD

    if use_celery:
        try:
            async_res = generate_xlsx_export_task.apply_async(
                args=[product_dicts, specs_by_category, platform, user_id],
                queue="xlsx_export",
            )
            deadline = time.monotonic() + CELERY_XLSX_TIMEOUT_SEC
            while time.monotonic() < deadline:
                if async_res.ready():
                    if async_res.successful():
                        res_data = async_res.result or {}
                        file_path = res_data.get("file_path")
                        filename = res_data.get("filename") or f"{platform}_export.xlsx"
                        if file_path and Path(file_path).is_file():
                            data = await asyncio.to_thread(Path(file_path).read_bytes)
                            try:
                                await asyncio.to_thread(Path(file_path).unlink, True)
                            except Exception:
                                pass
                            return data, filename
                    break
                await asyncio.sleep(0.25)
            logger.warning(
                f"⚠️ Celery xlsx_export не ответил вовремя для task={async_res.id}, "
                f"переключаюсь на резервную сборку в asyncio.to_thread"
            )
        except Exception as e:
            logger.warning(
                f"⚠️ Не удалось отправить задачу в очередь xlsx_export ({e}), "
                f"выполняю через asyncio.to_thread"
            )

    return await asyncio.to_thread(
        generate_export, product_dicts, specs_by_category, platform
    )


# ==================== ЭТАЛОННЫЕ ШАБЛОНЫ (Мультиплатформенные) ====================


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
    cat = await _normalize_category_name(db, category_name, pl)

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
    cat = await _normalize_category_name(db, category_name, pl)
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
    cat = await _normalize_category_name(db, category_name, pl)
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
async def delete_official_template(
    category_name: str = "Универсальный (все категории)",
    platform: str = Query("ozon"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Удаление эталона — только админ (было В-2 код-ревью: мог любой пользователь)."""
    pl = (platform or "ozon").lower().strip()
    cat = await _normalize_category_name(db, category_name, pl)
    deleted = template_filler.delete_official_template(cat, platform=pl)
    if not deleted:
        raise HTTPException(status_code=404, detail="Эталон не найден")
    logger.info(f"🗑 Эталон [{pl}] удалён: '{cat}' (пользователь {current_user.username})")
    return {"ok": True, "platform": pl, "category": cat}


# ==================== ПРЕДПРОСМОТР ВЫГРУЗКИ ====================


@limiter.limit("30/minute")
@router.get("/export/preview/{platform}")
async def export_preview(
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

    ids = _parse_product_ids(product_id, product_ids)
    products = await _get_products_for_export_async(
        db, current_user, status, selected_ids=ids, changed_since=changed_since
    )
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
            "incremental": {"new": 0, "changed": 0, "unchanged": 0, "enabled": changed_since},
        }

    validation = validate_products(products, platform)
    rows = build_rows(products[:10], platform)
    columns = list(rows[0].keys()) if rows else []

    # ✅ v4: сводка инкремента (новые/изменённые/без изменений) — для превью
    all_match = await _get_products_for_export_async(db, current_user, status, selected_ids=ids)
    incremental = await _incremental_stats(all_match)
    incremental["enabled"] = changed_since

    return {
        "success": True,
        "columns": columns,
        "rows": rows,
        "validation": validation,
        "incremental": incremental,
    }


# ==================== ШАБЛОН ВЫГРУЗКИ ====================


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
            headers={"Content-Disposition": _safe_disposition(filename)},
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
    for i, col in enumerate(ws[1]):
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
        headers={"Content-Disposition": _safe_disposition(filename)},
    )


# ==================== ФАЙЛ ДЛЯ ЛК ПЛОЩАДКИ ====================


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

    ids = _parse_product_ids(product_id, product_ids)
    products = await _get_products_for_export_async(
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

    # ✅ v4: пометить выгруженные товары (для «только изменённые»)
    await _mark_exported(db, [p["id"] for p in valid_products], platform)

    return StreamingResponse(
        output,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": _safe_disposition(filename)},
    )


# ==================== ВАЛИДАЦИЯ ПО СПЕКАМ ====================


@router.get("/export/validate/{platform}")
async def validate_export(
    platform: str,
    status: str = "all",
    product_id: int = Query(None),
    product_ids: str = Query(None),
    changed_since: bool = Query(False, description="✅ v4: только изменённые с последней выгрузки"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    ids = _parse_product_ids(product_id, product_ids)

    stmt = (
        select(Product)
        .options(
            selectinload(Product.attributes),
            selectinload(Product.variants),
        )
        .where(Product.user_id == current_user.id)
    )
    if ids:
        stmt = stmt.where(Product.id.in_(ids))
    elif status and status != "all":
        stmt = stmt.where(Product.status == status)

    res = await db.execute(stmt)
    products = res.scalars().all()

    # ✅ v4: сводка инкремента до фильтрации — для чекбокса «только изменённые»
    incremental = await _incremental_stats(products)
    incremental["enabled"] = changed_since

    if changed_since:
        products = [
            p
            for p in products
            if p.last_export_at is None
            or (p.updated_at and p.updated_at > p.last_export_at)
        ]

    if not products:
        return {
            "total": 0,
            "errors": 0,
            "warnings": 0,
            "issues": [],
            "missing_specs": [],
            "incremental": incremental,
        }

    product_dicts = [_product_to_dict(p) for p in products]

    categories = {
        (p["mapped_category"] or p["category"] or "Без категории") for p in product_dicts
    }
    spec_stmt = select(PlatformCategorySpec).where(
        PlatformCategorySpec.platform == platform,
        PlatformCategorySpec.category_name.in_(categories),
    )
    spec_res = await db.execute(spec_stmt)
    specs = spec_res.scalars().all()
    specs_by_name = {s.category_name: s.spec for s in specs}

    missing_specs = sorted(cat for cat in categories if cat not in specs_by_name)
    specs_by_category = {cat: specs_by_name.get(cat) for cat in categories}

    from services.spec_validator import validate_products_by_specs

    result = validate_products_by_specs(product_dicts, specs_by_category, platform)
    result["missing_specs"] = missing_specs
    result["incremental"] = incremental
    return result


# ==================== ОТЧЁТ ПО ВСЕМ ТОВАРАМ ====================


@limiter.limit("5/minute;50/day")
@router.get("/export/report")
async def export_migration_report(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    products = await _get_products_for_export_async(
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
        headers={"Content-Disposition": _safe_disposition(filename)},
    )


# ==================== XLSX v2 (Экспорт по шаблону эталона + очередь Celery) ====================


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
    if not status or status not in ("success", "pending", "processing", "error", "all"):
        status = "success"

    ids = _parse_product_ids(product_id, product_ids)

    stmt = (
        select(Product)
        .options(
            selectinload(Product.attributes),
            selectinload(Product.variants),
        )
        .where(Product.user_id == current_user.id)
    )
    if ids:
        stmt = stmt.where(Product.id.in_(ids))
        logger.info(f"📥 Экспорт выбранных товаров: ids={ids}, platform={platform}")
    elif status != "all":
        stmt = stmt.where(Product.status == status)

    # ✅ v4: инкрементальный фильтр — только новые/изменённые с прошлой выгрузки
    if changed_since:
        stmt = stmt.where(
            (Product.last_export_at.is_(None))
            | (Product.updated_at > Product.last_export_at)
        )

    res = await db.execute(stmt)
    products = res.scalars().all()

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

    product_dicts = [_product_to_dict(p) for p in products]
    specs_by_category = await _load_specs_by_category_async(db, product_dicts, platform)

    t0 = time.perf_counter()
    data, filename = await _run_xlsx_via_celery_or_thread(
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
    await _mark_exported(db, [p["id"] for p in product_dicts], platform)

    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": _safe_disposition(filename)},
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
    if not status or status not in ("success", "pending", "processing", "error", "all"):
        status = "success"

    ids = _parse_product_ids(product_id, product_ids)
    stmt = (
        select(Product)
        .options(
            selectinload(Product.attributes),
            selectinload(Product.variants),
        )
        .where(Product.user_id == current_user.id)
    )
    if ids:
        stmt = stmt.where(Product.id.in_(ids))
    elif status != "all":
        stmt = stmt.where(Product.status == status)

    res = await db.execute(stmt)
    products = res.scalars().all()
    if not products:
        raise HTTPException(status_code=400, detail="Нет товаров для выгрузки")

    product_dicts = [_product_to_dict(p) for p in products]
    specs_by_category = await _load_specs_by_category_async(db, product_dicts, platform)

    task = generate_xlsx_export_task.apply_async(
        args=[product_dicts, specs_by_category, platform, current_user.id],
        queue="xlsx_export",
    )
    # IDOR-защита (В-2): привязываем task_id к владельцу
    _register_export_task_owner(task.id, current_user.id)
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
    _assert_export_task_owner(task_id, current_user)
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
    _assert_export_task_owner(task_id, current_user)

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
        headers={"Content-Disposition": _safe_disposition(filename)},
    )