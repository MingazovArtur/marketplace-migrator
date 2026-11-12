"""
Предпросмотр выгрузки и валидация по спекам площадок.

Вынесено из монолита routers/export.py (Р1). Три одинаковых inline-запроса
выборки товаров (превью-инкремент, валидация, XLSX v2) заменены общим
load_user_products из _queries — фильтры (ids/status/changed_since)
сохранены точь-в-точь.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.platforms import Platform
from core.rate_limit import limiter
from database.models import PlatformCategorySpec, User
from database.session import get_async_db
from routers.export._queries import (
    get_products_for_export_async,
    incremental_stats,
    is_changed_since,
    load_user_products,
    product_to_dict,
)
from routers.export._support import parse_product_ids
from services.export_builder import build_rows
from services.export_validator import validate_products
from services.spec_validator import validate_products_by_specs

router = APIRouter()


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

    ids = parse_product_ids(product_id, product_ids)

    # ✅ О2: ОДНА выборка вместо двух. Берём всё подходящее по фильтрам
    # (ids/status) — по нему же считается сводка инкремента, — затем чекбокс
    # «только изменённые» сужает список в Python (как в validate_export).
    # Бонус: при пустом инкременте сводка теперь честная, а не нулевая.
    all_match = await get_products_for_export_async(db, current_user, status, selected_ids=ids)
    incremental = incremental_stats(all_match)
    incremental["enabled"] = changed_since

    products = all_match if not changed_since else [p for p in all_match if is_changed_since(p)]

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
            "incremental": incremental,
        }

    validation = validate_products(products, platform)
    rows = build_rows(products[:10], platform)
    columns = list(rows[0].keys()) if rows else []

    return {
        "success": True,
        "columns": columns,
        "rows": rows,
        "validation": validation,
        "incremental": incremental,
    }


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
    # ORM-выборка ДО фильтрации changed_since: сводка инкремента считается
    # по всем подходящим товарам, затем список сужается.
    ids = parse_product_ids(product_id, product_ids)
    products = await load_user_products(db, current_user, status, selected_ids=ids)

    # ✅ v4: сводка инкремента до фильтрации — для чекбокса «только изменённые»
    incremental = incremental_stats(products)
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

    product_dicts = [product_to_dict(p) for p in products]
    specs_by_category, missing_specs = await _specs_for_products(db, product_dicts, platform)

    result = validate_products_by_specs(product_dicts, specs_by_category, platform)
    result["missing_specs"] = missing_specs
    result["incremental"] = incremental
    return result


async def _specs_for_products(
    db: AsyncSession, product_dicts: list[dict], platform: str
) -> tuple[dict[str, dict | None], list[str]]:
    """Спеки по категориям выборки + отсортированный список категорий без спек."""
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
    return specs_by_category, missing_specs
