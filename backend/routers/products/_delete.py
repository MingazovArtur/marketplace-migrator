"""Массовое удаление товаров: bulk-delete (один bulk DELETE вместо ORM-цикла,
P-5) и delete-all (требует confirm=true).

Вынесено без изменений из монолита routers/products.py (Р10).
"""

import contextlib
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from database.models import Product as ProductORM
from database.models import User
from database.repository import stats_repo
from database.session import get_async_db
from routers.products._support import BulkDeleteRequest, DeleteAllRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/products/bulk-delete")
async def bulk_delete_products(
    payload: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Массовое удаление товаров.
    Пользователь удаляет только свои; админ — любые.

    P-5 (неделя 3): один bulk DELETE вместо ORM-цикла (было: SELECT всех
    товаров в память + db.delete() по одному — N+1 запросов и O(N) памяти).
    Атрибуты и варианты сносит FK-каскад на стороне БД (ondelete=CASCADE).
    """
    if not payload.product_ids or len(payload.product_ids) == 0:
        raise HTTPException(status_code=400, detail="Не указаны товары для удаления")

    try:
        stmt = delete(ProductORM).where(ProductORM.id.in_(payload.product_ids))
        if current_user.role != "admin":
            stmt = stmt.where(ProductORM.user_id == current_user.id)

        res = await db.execute(stmt)
        await db.commit()

        deleted = res.rowcount
        skipped = len(payload.product_ids) - deleted

        logger.warning(
            f"🗑 Bulk delete: user={current_user.id} deleted={deleted} "
            f"requested={len(payload.product_ids)} skipped={skipped}"
        )
        with contextlib.suppress(Exception):
            stats_repo.record(
                user_id=current_user.id,
                operation="delete",
                platform=None,
                status="success",
                total_items=len(payload.product_ids),
                success_items=deleted,
                failed_items=skipped,
                duration_ms=0,
            )

        return {"success": True, "deleted": deleted, "skipped": skipped}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка bulk-удаления: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления товаров") from e


@router.post("/products/delete-all")
async def delete_all_products(
    payload: DeleteAllRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Удалить ВСЕ товары: пользователь — свои, админ — все в системе.
    Требует явного подтверждения confirm=true (UI спрашивает слово «УДАЛИТЬ»).

    P-5 (неделя 3): один bulk DELETE вместо загрузки ВСЕХ товаров в память
    и db.delete() по одному (у пользователя с 10 000 карточек это 10 000
    ORM-объектов + 10 000 DELETE-запросов).
    """
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Операция необратима. Передайте confirm=true для подтверждения.",
        )

    try:
        user_cond = None if current_user.role == "admin" else ProductORM.user_id == current_user.id

        count_stmt = select(func.count(ProductORM.id))
        del_stmt = delete(ProductORM)
        if user_cond is not None:
            count_stmt = count_stmt.where(user_cond)
            del_stmt = del_stmt.where(user_cond)

        # COUNT-запрос монолита сохранён (результат не используется с P-5:
        # счётчик берётся из rowcount), F841: имя total убрано
        await db.execute(count_stmt)
        res = await db.execute(del_stmt)
        await db.commit()

        deleted = res.rowcount

        logger.warning(
            f"🗑 DELETE ALL: user={current_user.id} role={current_user.role} " f"deleted={deleted}"
        )
        with contextlib.suppress(Exception):
            stats_repo.record(
                user_id=current_user.id,
                operation="delete_all",
                platform=None,
                status="success",
                total_items=deleted,
                success_items=deleted,
                failed_items=0,
                duration_ms=0,
            )

        return {"success": True, "deleted": deleted}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка полного удаления: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления товаров") from e
