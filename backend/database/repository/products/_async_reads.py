"""Асинхронный контур чтения (FastAPI, AsyncSession + asyncpg):
список с пагинацией, одиночный товар, статистика одним SQL-запросом."""

from sqlalchemy import asc, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Product


class _AsyncReadsMixin:
    """get_all_async / get_by_id_async / get_stats_async (Р14)."""

    async def get_all_async(
        self,
        db: AsyncSession,
        user_id: int = None,
        is_admin: bool = False,
        search: str | None = None,
        status: str | None = None,
        source: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        """Неблокирующее получение товаров с фильтрацией, сортировкой и пагинацией."""
        count_stmt = select(func.count(Product.id))
        count_stmt = self._apply_async_filters(
            count_stmt, user_id, is_admin, search, status, source
        )
        total_res = await db.execute(count_stmt)
        total = int(total_res.scalar() or 0)

        stmt = select(Product).options(
            selectinload(Product.attributes),
            selectinload(Product.variants),
        )
        stmt = self._apply_async_filters(stmt, user_id, is_admin, search, status, source)

        sort_column = getattr(Product, sort_by, Product.created_at)
        stmt = stmt.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))
        stmt = stmt.offset(skip).limit(limit)

        res = await db.execute(stmt)
        products = res.scalars().all()

        return {
            "total": total,
            "products": [self._to_dict(p) for p in products],
        }

    async def get_by_id_async(
        self, db: AsyncSession, product_id: int, user_id: int = None, is_admin: bool = False
    ) -> dict | None:
        """Неблокирующее получение ОДНОГО товара по ID (модалки миграции/редактирования).

        Важно: читает СВЕЖИЕ данные из БД, а не из кэша фронтенда — после
        «Заполнить пропуски» / массового обновления цена и поля уже актуальны.
        """
        stmt = (
            select(Product)
            .options(selectinload(Product.attributes), selectinload(Product.variants))
            .where(Product.id == product_id)
        )
        if not is_admin and user_id is not None:
            stmt = stmt.where(Product.user_id == user_id)

        res = await db.execute(stmt)
        product = res.scalars().first()
        return self._to_dict(product)

    async def get_stats_async(
        self,
        db: AsyncSession,
        user_id: int = None,
        is_admin: bool = False,
    ) -> dict:
        """Неблокирующее получение статистики одним SQL-запросом."""
        stmt = select(
            func.count(Product.id).label("total"),
            func.coalesce(
                func.sum(case((Product.status == "pending", 1), else_=0)), 0
            ).label("pending"),
            func.coalesce(
                func.sum(case((Product.status == "success", 1), else_=0)), 0
            ).label("success"),
            func.coalesce(
                func.sum(case((Product.status == "error", 1), else_=0)), 0
            ).label("error"),
            func.coalesce(
                func.sum(case((Product.status == "processing", 1), else_=0)), 0
            ).label("processing"),
        )
        if not is_admin and user_id is not None:
            stmt = stmt.where(Product.user_id == user_id)

        res = await db.execute(stmt)
        row = res.one()
        return {
            "total": int(row.total or 0),
            "pending": int(row.pending or 0),
            "success": int(row.success or 0),
            "error": int(row.error or 0),
            "processing": int(row.processing or 0),
        }
