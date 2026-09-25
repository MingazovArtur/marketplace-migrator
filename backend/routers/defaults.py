"""Дефолты экспорта + массовое дозаполнение пропусков."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_current_user
from core.rate_limit import limiter
from database.models import ExportDefault, Product, User
from database.repository import repo
from database.session import SessionLocal
from services import defaults_service

logger = __import__("logging").getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Defaults"])

SAVE_FIELDS = (
    "vat_rate", "okpd_code",
    "package_weight_grams", "package_width_mm", "package_height_mm", "package_length_mm",
    "brand", "marking", "price_default",
)


class DefaultsPayload(BaseModel):
    category_name: Optional[str] = None        # None = глобальные
    vat_rate: Optional[str] = None
    okpd_code: Optional[str] = None
    package_weight_grams: Optional[int] = None
    package_width_mm: Optional[int] = None
    package_height_mm: Optional[int] = None
    package_length_mm: Optional[int] = None
    brand: Optional[str] = None
    marking: Optional[str] = None
    price_default: Optional[float] = None      # ✅ цена по умолчанию (только для нулевых)


def _row_to_dict(row: Optional[ExportDefault]) -> Optional[dict]:
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
def get_defaults(current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        rows = db.query(ExportDefault).filter(ExportDefault.user_id == current_user.id).all()
        glob = next((_row_to_dict(r) for r in rows if r.category_name is None), None)
        cats = [_row_to_dict(r) for r in rows if r.category_name is not None]
        return {"global": glob, "categories": cats}
    finally:
        db.close()


@router.put("/defaults")
def save_defaults(payload: DefaultsPayload, current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        row = (
            db.query(ExportDefault)
            .filter(
                ExportDefault.user_id == current_user.id,
                ExportDefault.category_name.is_(None)
                if payload.category_name is None
                else ExportDefault.category_name == payload.category_name.strip(),
            )
            .first()
        )
        if not row:
            row = ExportDefault(
                user_id=current_user.id,
                category_name=payload.category_name.strip() if payload.category_name else None,
            )
            db.add(row)
        for f in SAVE_FIELDS:
            setattr(row, f, getattr(payload, f))
        db.commit()
        db.refresh(row)
        return {"ok": True, "defaults": _row_to_dict(row)}
    finally:
        db.close()


@router.delete("/defaults/category")
def delete_category_defaults(
    category_name: str, current_user: User = Depends(get_current_user)
):
    db = SessionLocal()
    try:
        row = (
            db.query(ExportDefault)
            .filter(ExportDefault.user_id == current_user.id,
                    ExportDefault.category_name == category_name.strip())
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Дефолты категории не найдены")
        db.delete(row)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.get("/defaults/gaps")
def get_gaps(status: str = "all", current_user: User = Depends(get_current_user)):
    return defaults_service.compute_gaps(current_user.id, status)


@limiter.limit("10/minute")
@router.post("/products/apply-defaults")
def apply_defaults(
    request: Request,
    status: str = "all",
    current_user: User = Depends(get_current_user),
):
    """
    ✅ Массовое дозаполнение: для ВСЕХ товаров пользователя дописывает пустые
    поля (НДС, ТН ВЭД, ОВХ, вес, цена-по-умолчанию) из дефолтов категории/глобальных.
    Один клик на 5000 товаров.

    ✅ Оптимизация: dict товара собирается прямо из ORM-объекта (без repo.get_by_id),
    поэтому на каждый товар остаётся только один UPDATE при наличии обновлений.
    """
    db = SessionLocal()
    try:
        q = db.query(Product).filter(Product.user_id == current_user.id)
        if status and status != "all":
            q = q.filter(Product.status == status)
        products = q.all()

        updated = 0
        field_counter: dict = {}
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
            repo.update(p.id, updates, user_id=current_user.id)
            updated += 1
            for k in updates:
                field_counter[k] = field_counter.get(k, 0) + 1

        logger.info(f"🩹 apply-defaults: обновлено {updated} из {len(products)}; поля: {field_counter}")
        return {"updated": updated, "total": len(products), "fields": field_counter}
    finally:
        db.close()