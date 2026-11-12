"""Фильтры выборки товаров: одинаковая семантика для синхронного (Query)
и асинхронного (Select) контуров — владелец/админ, поиск, статус, источник."""

from database.models import Product


class _FiltersMixin:
    """_apply_filters / _apply_async_filters (Р14)."""

    @staticmethod
    def _apply_filters(query, user_id, is_admin, search, status, source):
        if not is_admin and user_id is not None:
            query = query.filter(Product.user_id == user_id)
        if search:
            query = query.filter(Product.name.ilike(f"%{search}%"))
        if status:
            query = query.filter(Product.status == status)
        if source:
            query = query.filter(Product.source.ilike(f"%{source}%"))
        return query

    @staticmethod
    def _apply_async_filters(stmt, user_id, is_admin, search, status, source):
        if not is_admin and user_id is not None:
            stmt = stmt.where(Product.user_id == user_id)
        if search:
            stmt = stmt.where(Product.name.ilike(f"%{search}%"))
        if status:
            stmt = stmt.where(Product.status == status)
        if source:
            stmt = stmt.where(Product.source.ilike(f"%{source}%"))
        return stmt
