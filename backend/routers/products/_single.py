"""Одиночный товар: точечная правка (PATCH), логистика (PUT /{id}/logistics),
чтение (GET) и удаление (DELETE). Правки пишут undo-снапшоты.

Вынесено без изменений из монолита routers/products.py (Р10).
"""

import contextlib
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from database.models import Product as ProductORM
from database.models import User
from database.repository import repo, stats_repo
from database.session import get_async_db
from models.schemas import ProductLogisticsUpdate
from routers.products._support import ProductUpdateRequest
from services.edit_history import write_edit_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()


@router.patch("/products/{product_id}")
async def update_product(
    product_id: int,
    payload: ProductUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Точечное обновление товара: название / цена / категория назначения.

    Зачем: в окне «Миграция карточки» раньше была только кнопка «Мигрировать» —
    нельзя было указать цену и просто сохранить её без запуска миграции
    (товары из файлов часто приходят с ценой 0, и миграция блокировалась).
    Категория, как и в bulk-update, пишется в mapped_category.
    """
    if payload.name is None and payload.price is None and payload.category is None:
        raise HTTPException(status_code=400, detail="Не указаны поля для обновления")

    if payload.name is not None and not payload.name.strip():
        raise HTTPException(status_code=400, detail="Название не может быть пустым")

    if payload.price is not None and not (payload.price > 0):
        raise HTTPException(status_code=400, detail="Цена должна быть больше 0 ₽")

    stmt = select(ProductORM).where(
        ProductORM.id == product_id,
        ProductORM.user_id == current_user.id,
    )
    p = (await db.execute(stmt)).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")

    # ✅ v4: какие поля РЕАЛЬНО изменятся (для undo-снапшота)
    old_price = float(p.price or 0)
    will_change = []
    if payload.name is not None and payload.name.strip() != p.name:
        will_change.append("name")
    if payload.price is not None and float(payload.price) != old_price:
        will_change.append("price")
    if payload.category is not None and (payload.category.strip() or None) != p.mapped_category:
        will_change.append("category")

    if will_change:
        await write_edit_snapshot(
            db,
            current_user.id,
            [p],
            will_change,
            action="edit",
            label=f"Правка товара #{p.id}: {', '.join(will_change)}",
        )

    updated = []
    if payload.name is not None and payload.name.strip() != p.name:
        p.name = payload.name.strip()
        updated.append("name")
    if payload.price is not None and float(payload.price) != float(p.price or 0):
        p.price = round(float(payload.price), 2)
        updated.append("price")
    if payload.category is not None:
        new_cat = payload.category.strip() or None
        if new_cat != p.mapped_category:
            p.mapped_category = new_cat
            updated.append("category")

    if updated:
        await db.commit()
        logger.info(f"✏️ Update product {product_id}: user={current_user.id} fields={updated}")

    return {
        "success": True,
        "updated_fields": updated,
        "product": {
            "id": p.id,
            "name": p.name,
            "price": float(p.price or 0),
            "mapped_category": p.mapped_category,
        },
    }


@router.put("/products/{product_id}/logistics")
async def update_product_logistics(
    product_id: int,
    payload: ProductLogisticsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Логистические данные товара: штрихкод, габариты упаковки, НДС, ОКПД."""
    try:
        stmt = select(ProductORM).where(
            ProductORM.id == product_id,
            ProductORM.user_id == current_user.id,
        )
        res = await db.execute(stmt)
        product = res.scalars().first()

        if not product:
            raise HTTPException(status_code=404, detail="Товар не найден")

        updates = payload.model_dump(exclude_unset=True)
        logger.warning(f"📦 logistics PUT id={product_id} user={current_user.id} updates={updates}")

        if not updates:
            logger.warning(
                f"📦 logistics PUT id={product_id}: payload пустой — ничего не сохраняем"
            )
            return {"success": True, "product_id": product.id, "updated_fields": 0}

        # ✅ v4: undo-снапшот прежней логистики (только реально затронутые поля)
        snap_fields = [f for f in updates if hasattr(product, f)]
        if snap_fields:
            await write_edit_snapshot(
                db,
                current_user.id,
                [product],
                snap_fields,
                action="logistics",
                label=f"Логистика товара #{product.id}: {', '.join(snap_fields)}",
            )

        for field, value in updates.items():
            if not hasattr(product, field):
                logger.error(f"❌ Поле {field} отсутствует в модели Product!")
                continue
            setattr(product, field, value)

        await db.commit()
        await db.refresh(product)

        logger.warning(
            f"📦 logistics SAVED id={product_id}: "
            f"vat={product.vat_rate} okpd={product.okpd_code} "
            f"pkg_w={product.package_weight_grams} pkg_wxhxl="
            f"({product.package_width_mm}x{product.package_height_mm}x{product.package_length_mm}) "
            f"barcode={product.barcode}"
        )

        return {
            "success": True,
            "product_id": product.id,
            "updated_fields": len(updates),
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Ошибка обновления логистики товара {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обновления логистики: {e}") from e


@router.get("/products/{product_id}")
async def get_product_by_id(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Получить ОДИН товар со свежими данными из БД.

    Нужен модалкам (миграция/логистика/фото), которые раньше получали товар
    из кэша списка на фронте: после «Заполнить пропуски» или массового
    обновления кэш мог показывать устаревшую цену (баг «в окне миграции
    цена 0, хотя дефолт уже применён»).
    """
    product = await repo.get_by_id_async(
        db,
        product_id=product_id,
        user_id=current_user.id,
        is_admin=current_user.role == "admin",
    )
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")
    return product


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Удалить товар (только если он принадлежит текущему пользователю; админ — любой)."""
    stmt = select(ProductORM).where(ProductORM.id == product_id)
    if current_user.role != "admin":
        stmt = stmt.where(ProductORM.user_id == current_user.id)

    res = await db.execute(stmt)
    product = res.scalars().first()

    if product:
        await db.delete(product)
        await db.commit()
        logger.warning(f"🗑 Delete product {product_id} by user={current_user.id}")
        with contextlib.suppress(Exception):
            stats_repo.record(
                user_id=current_user.id,
                operation="delete",
                platform=None,
                status="success",
                total_items=1,
                success_items=1,
                failed_items=0,
                duration_ms=0,
            )
        return {"success": True}

    raise HTTPException(status_code=404, detail="Товар не найден или не принадлежит вам")
