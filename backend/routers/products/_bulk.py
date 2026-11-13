"""Массовые правки товаров: bulk-update / bulk-preview / bulk-undo + лента
edit-history (undo-снапшоты пишутся через services/edit_history).

Вынесено без изменений из монолита routers/products.py (Р10).
"""

import contextlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from database.models import Product as ProductORM
from database.models import User
from database.repository import stats_repo
from database.session import get_async_db
from models.schemas import ProductBulkUpdate
from routers.products._support import (
    UndoRequest,
    _validate_category_against_specs_async,
)
from services.bulk_ops import compute_preview
from services.edit_history import list_edit_history, undo_snapshot, write_edit_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()


@router.put("/products/bulk-update")
async def bulk_update_products(
    request: ProductBulkUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Массовое обновление цены/бренда/категории назначения для выбранных товаров.

    ✅ Категория назначения пишется в mapped_category (для экспорта), а не в category.
    Миграция подхватывает её по приоритету 2 цепочки.
    """
    if not request.product_ids or len(request.product_ids) == 0:
        raise HTTPException(status_code=400, detail="Не указаны товары для обновления")

    if all(
        v is None for v in (request.price, request.price_percent, request.brand, request.category)
    ):
        raise HTTPException(status_code=400, detail="Не указаны поля для обновления")

    # ✅ Валидация категории назначения по спекам (не блокирующая)
    category_warning = None
    if request.category is not None and request.category.strip():
        spec_check = await _validate_category_against_specs_async(db, request.category)
        if not spec_check["exists"]:
            category_warning = (
                f"Категория «{request.category}» не найдена в спеках ни одной площадки. "
                f"Миграция завершится ошибкой для этих товаров."
            )
            logger.warning(f"⚠️ {category_warning}")
        else:
            logger.info(
                f"✅ Категория «{request.category}» есть в спеках площадок: "
                f"{', '.join(spec_check['platforms'])}"
            )

    updated = 0
    updated_ids: list[int] = []
    user_id = current_user.id

    stmt = select(ProductORM).where(
        ProductORM.id.in_(request.product_ids),
        ProductORM.user_id == user_id,
    )
    res = await db.execute(stmt)
    products_by_id = {p.id: p for p in res.scalars().all()}

    # ✅ v4: undo-снапшот через сервис истории правок (ротация внутри)
    snapshot = None
    if products_by_id:
        changed_fields = [
            name
            for name in ("price", "price_percent", "brand", "category")
            if getattr(request, name, None) is not None
        ]
        snapshot = await write_edit_snapshot(
            db,
            user_id,
            list(products_by_id.values()),
            changed_fields,
            action="bulk_update",
            label=f"Массовое обновление: {', '.join(changed_fields)} ({len(products_by_id)} тов.)",
        )

    for pid in request.product_ids:
        p = products_by_id.get(pid)
        if not p:
            logger.debug(f"⏭ Товар {pid} пропущен: не принадлежит пользователю {user_id}")
            continue

        has_changes = False

        # --- Цена ---
        if request.price_percent is not None:
            base_price = float(p.price or 0)
            p.price = round(base_price * (1 + request.price_percent / 100), 2)
            has_changes = True
        elif request.price is not None:
            p.price = float(request.price)
            has_changes = True

        # --- Бренд ---
        if request.brand is not None:
            p.brand = request.brand.strip() or None
            has_changes = True

        # --- ✅ Категория назначения (в mapped_category, не в category) ---
        if request.category is not None:
            p.mapped_category = request.category.strip() or None
            has_changes = True

        if has_changes:
            updated += 1
            updated_ids.append(pid)

    if updated == 0 and snapshot is not None:
        # Ничего не изменилось — снапшот не нужен
        await db.rollback()
    else:
        await db.commit()

    # ✅ Список изменённых полей считаем отдельно — выражения f-string
    #    не могут продолжаться в соседнем строковом литерале
    changed_fields = snapshot.payload["fields"] if snapshot else []
    logger.warning(
        f"✏️ Bulk update: user={current_user.id} "
        f"updated={updated}/{len(request.product_ids)} fields={changed_fields}"
    )

    with contextlib.suppress(Exception):
        stats_repo.record(
            user_id=current_user.id,
            operation="bulk_update",
            platform=None,
            status="success",
            total_items=len(request.product_ids),
            success_items=updated,
            failed_items=len(request.product_ids) - updated,
            duration_ms=0,
        )

    return {
        "success": True,
        "updated": updated,
        "updated_ids": updated_ids,
        "category_warning": category_warning,
    }


@router.post("/products/bulk-preview")
async def bulk_preview_products(
    request: ProductBulkUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Предпросмотр массового обновления БЕЗ записи: что случится с ценами
    и валидна ли категория назначения. Вызывается модалкой на лету.
    """
    if not request.product_ids:
        raise HTTPException(status_code=400, detail="Не указаны товары для предпросмотра")

    if all(
        v is None for v in (request.price, request.price_percent, request.brand, request.category)
    ):
        raise HTTPException(status_code=400, detail="Не указаны поля для предпросмотра")

    stmt = select(ProductORM).where(
        ProductORM.id.in_(request.product_ids),
        ProductORM.user_id == current_user.id,
    )
    products = (await db.execute(stmt)).scalars().all()

    preview = compute_preview(
        products, price=request.price, price_percent=request.price_percent
    )

    category_info = None
    if request.category is not None and request.category.strip():
        spec_check = await _validate_category_against_specs_async(db, request.category)
        category_info = {
            "valid": spec_check["exists"],
            "platforms": spec_check["platforms"],
        }

    return {"success": True, "preview": preview, "category": category_info}


@router.post("/products/bulk-undo")
async def bulk_undo_products(
    payload: UndoRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    ✅ v4: отмена операции правки товаров (последней или по snapshot_id).
    Восстанавливает прежние значения РОВНО тех полей, что менялись.
    Товары, удалённые после правки, пропускаются.
    """
    result = await undo_snapshot(
        db, current_user.id, snapshot_id=payload.snapshot_id if payload else None
    )
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("detail", "Нет изменений для отмены"))

    await db.commit()

    total = result["restored"] + result["skipped_missing"]
    with contextlib.suppress(Exception):
        stats_repo.record(
            user_id=current_user.id,
            operation="bulk_undo",
            platform=None,
            status="success",
            total_items=total,
            success_items=result["restored"],
            failed_items=result["skipped_missing"],
            duration_ms=0,
        )

    return {
        "success": True,
        "restored": result["restored"],
        "skipped_missing": result["skipped_missing"],
        "fields": result.get("fields", []),
        "label": result.get("label"),
        "snapshot_id": result.get("snapshot_id"),
    }


@router.get("/products/edit-history")
async def get_edit_history(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """✅ v4: лента последних операций правки товаров (аудит + undo-кнопки)."""
    return await list_edit_history(db, current_user.id, limit=limit)
