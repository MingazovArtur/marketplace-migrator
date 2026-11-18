"""Аналитика селлера: заполненность, категории, история правок.

Данные пользователя (админ здесь НЕ видит чужое — общая статистика
сервиса живёт в /api/admin/stats). Заполненность считается по всем
товарам пользователя в памяти: объёмы «сотни товаров на пользователя»
это покрывают без агрегирующего SQL.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Query

from core.auth import get_current_user
from core.time import utcnow
from database.models import BulkEditSnapshot, Product, User
from database.session import SessionLocal
from services.analytics import compute_categories, compute_fill

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

# Колонки, нужные вычислениям заполненности (лишнее не тянем: описания
# и JSON-фото не запрашиваем, только photos_count)
_PRODUCT_COLUMNS = (
    Product.id,
    Product.name,
    Product.price,
    Product.brand,
    Product.category,
    Product.mapped_category,
    Product.barcode,
    Product.weight_grams,
    Product.package_weight_grams,
    Product.package_width_mm,
    Product.package_height_mm,
    Product.package_length_mm,
    Product.vat_rate,
    Product.okpd_code,
    Product.sku,
    Product.stock,
    Product.photos_count,
    Product.description,
)


def _load_user_products(db, user_id: int) -> list[dict]:
    rows = db.query(*_PRODUCT_COLUMNS).filter(Product.user_id == user_id).all()
    return [dict(row._mapping) for row in rows]


@router.get("/fill")
def fill_report(current_user: User = Depends(get_current_user)):
    """Заполненность полей товаров: % по каждому полю, средняя и готовность к экспорту."""
    db = SessionLocal()
    try:
        products = _load_user_products(db, current_user.id)
        data = compute_fill(products)
        return {"success": True, **data}
    finally:
        db.close()


@router.get("/categories")
def categories_report(current_user: User = Depends(get_current_user)):
    """Срез по категориям: товаров, средняя цена, заполненность, маппинг."""
    db = SessionLocal()
    try:
        products = _load_user_products(db, current_user.id)
        return {"success": True, "categories": compute_categories(products)}
    finally:
        db.close()


@router.get("/edits")
def edits_report(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
):
    """История правок (bulk_edit_snapshots): по дням, по типам, последние."""
    db = SessionLocal()
    try:
        since = utcnow() - timedelta(days=days)
        snapshots = (
            db.query(BulkEditSnapshot)
            .filter(
                BulkEditSnapshot.user_id == current_user.id,
                BulkEditSnapshot.created_at >= since,
            )
            .order_by(BulkEditSnapshot.created_at.desc())
            .all()
        )

        # Плотный ряд по дням (нули включительно) — фронт рисует бары без дыр
        by_day = {}
        for i in range(days):
            d = (utcnow() - timedelta(days=days - 1 - i)).date()
            by_day[d.isoformat()] = {"date": d.isoformat(), "count": 0, "undone": 0}
        by_action: dict = {}
        for s in snapshots:
            key = s.created_at.date().isoformat()
            if key in by_day:
                by_day[key]["count"] += 1
                if s.undone:
                    by_day[key]["undone"] += 1
            by_action.setdefault(s.action, {"action": s.action, "count": 0, "undone": 0})
            by_action[s.action]["count"] += 1
            if s.undone:
                by_action[s.action]["undone"] += 1

        recent = [
            {
                "id": s.id,
                "action": s.action,
                "label": s.label,
                "undone": bool(s.undone),
                "items": len((s.payload or {}).get("items", [])),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snapshots[:10]
        ]

        return {
            "success": True,
            "period_days": days,
            "total": len(snapshots),
            "by_day": list(by_day.values()),
            "by_action": sorted(by_action.values(), key=lambda a: -a["count"]),
            "recent": recent,
        }
    finally:
        db.close()
