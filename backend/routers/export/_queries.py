"""
Асинхронные выборки товаров и спек для экспорта (без HTTP-логики).

Вынесено из монолита routers/export.py (Р1). Два режима выборки,
существовавшие в монолите, сохранены без изменения поведения:

  - get_products_for_export_async — с обходом для админа (видит всех),
    лимитом и сортировкой; использовалась превью/выгрузкой/отчётом;
  - load_user_products — строгий фильтр по текущему пользователю
    (даже для админа), без лимита; использовалась XLSX v2, async-выгрузкой
    и валидацией inline-блоками запросов.
"""

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import PlatformCategorySpec, Product, User

logger = logging.getLogger(__name__)


async def normalize_category_name(db: AsyncSession, name: str, platform: str = "ozon") -> str:
    raw = (name or "").strip()
    if not raw or raw.lower() in ("универсальный", "общий", "все категории", "default", "all"):
        return "Универсальный (все категории)"
    parts = [p.strip() for p in re.split(r"[>/\\]", raw) if p.strip()]
    candidate = " / ".join(parts[-2:]) if len(parts) >= 2 else raw

    stmt = select(PlatformCategorySpec).where(
        PlatformCategorySpec.platform == platform,
        PlatformCategorySpec.category_name == candidate,
    )
    res = await db.execute(stmt)
    row = res.scalars().first()
    return row.category_name if row else candidate


def product_to_dict(p: Product) -> dict:
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
        "attributes": [{"name": a.name, "value": a.value} for a in (p.attributes or [])],
        "variants": [
            {"sku": v.sku, "size": v.size, "color": v.color, "price": v.price}
            for v in (p.variants or [])
        ],
        # ✅ v4: для инкрементального экспорта (сводка «новые/изменённые»)
        "last_export_at": getattr(p, "last_export_at", None),
        "last_export_platform": getattr(p, "last_export_platform", None),
        "updated_at": getattr(p, "updated_at", None),
    }


async def get_products_for_export_async(
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
            (Product.last_export_at.is_(None)) | (Product.updated_at > Product.last_export_at)
        )

    res = await db.execute(stmt)
    products = res.scalars().all()
    return [product_to_dict(p) for p in products]


async def load_user_products(
    db: AsyncSession,
    current_user: User,
    status: str,
    selected_ids: list[int] | None = None,
    changed_since: bool = False,
) -> list[Product]:
    """Строгая выборка товаров ТОЛЬКО текущего пользователя (без админ-обхода).

    Обобщает три одинаковых inline-запроса из монолита (XLSX v2,
    async-постановка, валидация). Возвращает ORM-объекты с предзагруженными
    attributes/variants: валидации нужен ORM для сводки инкремента ДО
    фильтрации, XLSX — словари (product_to_dict) после.
    """
    stmt = (
        select(Product)
        .options(
            selectinload(Product.attributes),
            selectinload(Product.variants),
        )
        .where(Product.user_id == current_user.id)
    )
    if selected_ids:
        stmt = stmt.where(Product.id.in_(selected_ids))
    elif status and status != "all":
        stmt = stmt.where(Product.status == status)

    if changed_since:
        stmt = stmt.where(
            (Product.last_export_at.is_(None)) | (Product.updated_at > Product.last_export_at)
        )

    res = await db.execute(stmt)
    return list(res.scalars().all())


def incremental_stats(products: list) -> dict:
    """✅ v4: сводка для фильтра «только изменённые»: новые/изменённые/без изменений.

    Принимает ORM-объекты или словари product_to_dict (в словаре поля
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


def is_changed_since(p: dict) -> bool:
    """✅ О2: инкрементальный предикат для словарей product_to_dict:
    товар «новый/изменённый», если ещё не выгружался или менялся после выгрузки.
    Тот же критерий, что в SQL-фильтре и в validate_export (ORM-вариант).
    """
    last_exp = p.get("last_export_at")
    updated = p.get("updated_at")
    return last_exp is None or bool(updated and updated > last_exp)


async def mark_exported(db: AsyncSession, product_ids: list[int], platform: str) -> None:
    """✅ v4: зафиксировать факт выгрузки (для последующих инкрементальных экспортов).

    Не бросает исключений: пометка — вспомогательная операция, файл уже отдан.
    """
    if not product_ids:
        return
    try:
        now = datetime.now(UTC).replace(tzinfo=None)
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


async def load_specs_by_category(
    db: AsyncSession, product_dicts: list[dict], platform: str
) -> dict[str, dict | None]:
    categories = {(p["mapped_category"] or p["category"] or "Без категории") for p in product_dicts}
    spec_stmt = select(PlatformCategorySpec).where(
        PlatformCategorySpec.platform == platform,
        PlatformCategorySpec.category_name.in_(categories),
    )
    spec_res = await db.execute(spec_stmt)
    specs = spec_res.scalars().all()
    specs_by_name = {s.category_name: s.spec for s in specs}
    return {cat: specs_by_name.get(cat) for cat in categories}
