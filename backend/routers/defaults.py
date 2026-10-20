"""
Дефолты экспорта + массовое дозаполнение пропусков.
✅ v2 (AsyncSession + asyncpg): все эндпоинты переведены на неблокирующую работу с БД.
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.rate_limit import limiter
from database.models import ExportDefault, Product, User
from database.session import get_async_db
from services import defaults_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Defaults"])

SAVE_FIELDS = (
    "vat_rate",
    "okpd_code",
    "package_weight_grams",
    "package_width_mm",
    "package_height_mm",
    "package_length_mm",
    "brand",
    "marking",
    "price_default",
)


class DefaultsPayload(BaseModel):
    category_name: str | None = None  # None = глобальные
    vat_rate: str | None = None
    okpd_code: str | None = None
    package_weight_grams: int | None = None
    package_width_mm: int | None = None
    package_height_mm: int | None = None
    package_length_mm: int | None = None
    brand: str | None = None
    marking: str | None = None
    price_default: float | None = None  # цена по умолчанию (только для нулевых)


class ApplyDefaultsPayload(BaseModel):
    product_ids: list[int] | None = None
    status: str | None = None


def _row_to_dict(row: ExportDefault | None) -> dict | None:
    if not row:
        return None
    return {
        "category_name": row.category_name,
        "vat_rate": row.vat_rate,
        "okpd_code": row.okpd_code,
        "package_weight_grams": row.package_weight_grams,
        "package_width_mm": row.package_width_mm,
        "package_height_mm": row.package_height_mm,
        "package_length_mm": row.package_length_mm,
        "brand": row.brand,
        "marking": row.marking,
        "price_default": float(row.price_default) if row.price_default is not None else None,
    }


@router.get("/defaults")
async def get_defaults(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(ExportDefault).where(ExportDefault.user_id == current_user.id)
    res = await db.execute(stmt)
    rows = res.scalars().all()

    glob = next((_row_to_dict(r) for r in rows if r.category_name is None), None)
    cats = [_row_to_dict(r) for r in rows if r.category_name is not None]
    return {"global": glob, "categories": cats}


@router.put("/defaults")
async def save_defaults(
    payload: DefaultsPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    cat_filter = (
        ExportDefault.category_name.is_(None)
        if payload.category_name is None
        else ExportDefault.category_name == payload.category_name.strip()
    )
    stmt = select(ExportDefault).where(
        ExportDefault.user_id == current_user.id,
        cat_filter,
    )
    res = await db.execute(stmt)
    row = res.scalars().first()

    if not row:
        row = ExportDefault(
            user_id=current_user.id,
            category_name=payload.category_name.strip() if payload.category_name else None,
        )
        db.add(row)

    for f in SAVE_FIELDS:
        setattr(row, f, getattr(payload, f))

    await db.commit()
    await db.refresh(row)
    return {"ok": True, "defaults": _row_to_dict(row)}


@router.delete("/defaults/category")
async def delete_category_defaults(
    category_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(ExportDefault).where(
        ExportDefault.user_id == current_user.id,
        ExportDefault.category_name == category_name.strip(),
    )
    res = await db.execute(stmt)
    row = res.scalars().first()

    if not row:
        raise HTTPException(status_code=404, detail="Дефолты категории не найдены")

    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.get("/defaults/gaps")
async def get_gaps(status: str = "all", current_user: User = Depends(get_current_user)):
    return defaults_service.compute_gaps(current_user.id, status)


@limiter.limit("10/minute")
@router.post("/products/apply-defaults")
async def apply_defaults(
    request: Request,
    status: str = "all",
    payload: ApplyDefaultsPayload | None = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    ✅ Массовое дозаполнение: дописывает пустые поля (НДС, ТН ВЭД, ОВХ, вес,
    цена-по-умолчанию) из дефолтов категории/глобальных.
    Поддерживает фильтр как по query-параметру status, так и по списку product_ids в теле запроса.
    Все обновления выполняются в одной неблокирующей транзакции.
    """
    effective_status = (payload.status if payload and payload.status else status) or "all"
    product_ids = payload.product_ids if payload else None

    stmt = select(Product).where(Product.user_id == current_user.id)
    if product_ids:
        stmt = stmt.where(Product.id.in_(product_ids))
    elif effective_status != "all":
        stmt = stmt.where(Product.status == effective_status)

    res = await db.execute(stmt)
    products = res.scalars().all()

    updated = 0
    field_counter: dict[str, int] = {}
    for p in products:
        pdict = {
            "id": p.id,
            "price": p.price,
            "vat_rate": p.vat_rate,
            "okpd_code": p.okpd_code,
            "package_weight_grams": p.package_weight_grams,
            "package_width_mm": p.package_width_mm,
            "package_height_mm": p.package_height_mm,
            "package_length_mm": p.package_length_mm,
            "category": p.category,
            "mapped_category": p.mapped_category,
        }
        updates = defaults_service.build_updates_for_product(pdict, current_user.id)
        if not updates:
            continue
        for k, v in updates.items():
            setattr(p, k, v)
            field_counter[k] = field_counter.get(k, 0) + 1
        updated += 1

    if updated:
        await db.commit()

    logger.info(
        f"🩹 apply-defaults: обновлено {updated} из {len(products)}; поля: {field_counter}"
    )
    return {"updated": updated, "total": len(products), "fields": field_counter}