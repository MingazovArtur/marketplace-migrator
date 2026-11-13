"""Синхронный контур чтения (Celery и сервисы, SessionLocal):
список с пагинацией, одиночный товар, поиск по external_id/sku,
пакетная выборка чанками (P-3), статистика одним SQL-запросом (P-6)."""

from sqlalchemy import asc, case, desc, func, select
from sqlalchemy.orm import selectinload

from database.models import Product
from database.session import SessionLocal


class _SyncReadsMixin:
    """get_all / get_by_id / find_by_external / get_by_ids / get_stats (Р14)."""

    def get_all(
        self,
        user_id: int = None,
        is_admin: bool = False,
        search: str | None = None,
        status: str | None = None,
        source: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ):
        """Получить товары с фильтрацией, сортировкой и пагинацией."""
        with SessionLocal() as db:
            # ✅ ОПТИМИЗАЦИЯ: Eager loading предотвращает N+1 запросов для attributes и variants
            query = db.query(Product).options(
                selectinload(Product.attributes), selectinload(Product.variants)
            )
            query = self._apply_filters(query, user_id, is_admin, search, status, source)

            total = query.count()

            sort_column = getattr(Product, sort_by, Product.created_at)
            query = query.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

            products = query.offset(skip).limit(limit).all()

            return {
                "total": total,
                "products": [self._to_dict(p) for p in products],
            }

    def get_by_id(self, product_id: int, user_id: int = None):
        """Получить товар по ID. Если указан user_id — проверяет владельца."""
        with SessionLocal() as db:
            # ✅ ОПТИМИЗАЦИЯ: Eager loading для модалок редактирования
            query = (
                db.query(Product)
                .options(selectinload(Product.attributes), selectinload(Product.variants))
                .filter(Product.id == product_id)
            )

            if user_id is not None:
                query = query.filter(Product.user_id == user_id)

            return self._to_dict(query.first())

    def find_by_external(
        self, user_id: int, source: str, external_id: str = None, sku: str = None
    ) -> dict | None:
        """Найти существующий товар по external_id или sku (для upsert при повторном импорте)."""
        with SessionLocal() as db:
            # ✅ ОПТИМИЗАЦИЯ: Eager loading на случай, если потребуется сериализация
            query = (
                db.query(Product)
                .options(selectinload(Product.attributes), selectinload(Product.variants))
                .filter(
                    Product.user_id == user_id,
                    Product.source == source,
                )
            )
            if external_id:
                query = query.filter(Product.external_id == external_id)
            elif sku:
                query = query.filter(Product.sku == sku)
            else:
                return None
            return self._to_dict(query.first())

    def get_by_ids(self, user_id: int, product_ids: list, chunk_size: int = 100) -> dict:
        """P-3: выборка пакета товаров одним selectinload-запросом на чанк
        вместо get_by_id() по одному (сессия на каждый товар → 1 на чанк).
        Возвращает {product_id: dict}."""
        result: dict = {}
        if not product_ids:
            return result
        with SessionLocal() as db:
            for offset in range(0, len(product_ids), chunk_size):
                chunk = product_ids[offset : offset + chunk_size]
                rows = (
                    db.query(Product)
                    .options(selectinload(Product.attributes), selectinload(Product.variants))
                    .filter(Product.user_id == user_id, Product.id.in_(chunk))
                    .all()
                )
                for p in rows:
                    result[p.id] = self._to_dict(p)
        return result

    def get_stats(self, user_id: int = None, is_admin: bool = False):
        """Статистика по товарам одним SQL-запросом (P-6).

        Раньше: 5 отдельных COUNT-запросов к одной таблице.
        """
        with SessionLocal() as db:
            stmt = select(
                func.count(Product.id).label("total"),
                func.coalesce(func.sum(case((Product.status == "pending", 1), else_=0)), 0).label(
                    "pending"
                ),
                func.coalesce(func.sum(case((Product.status == "success", 1), else_=0)), 0).label(
                    "success"
                ),
                func.coalesce(func.sum(case((Product.status == "error", 1), else_=0)), 0).label(
                    "error"
                ),
                func.coalesce(
                    func.sum(case((Product.status == "processing", 1), else_=0)), 0
                ).label("processing"),
            )
            if not is_admin and user_id is not None:
                stmt = stmt.where(Product.user_id == user_id)

            row = db.execute(stmt).one()
            return {
                "total": int(row.total or 0),
                "pending": int(row.pending or 0),
                "success": int(row.success or 0),
                "error": int(row.error or 0),
                "processing": int(row.processing or 0),
            }
