"""Запись товаров (синхронный контур): add/update/delete по одному,
bulk_update одним UPDATE, update_batch разными данными одной сессией (P-3)."""

from database.models import Product
from database.session import SessionLocal


class _WritesMixin:
    """add / update / bulk_update / update_batch / delete (Р14)."""

    def add(self, product_data):
        """Добавить новый товар. product_data должен содержать user_id."""
        with SessionLocal() as db:
            if hasattr(product_data, "model_dump"):
                data_dict = product_data.model_dump()
            else:
                data_dict = dict(product_data)
            data_dict.pop("id", None)

            if not data_dict.get("user_id"):
                raise ValueError("user_id обязателен при создании товара")

            new_product = Product(**data_dict)
            db.add(new_product)
            db.commit()
            db.refresh(new_product)
            return self._to_dict(new_product)

    def update(self, product_id: int, update_data: dict, user_id: int = None):
        """Обновить товар. Если указан user_id — проверяет владельца."""
        with SessionLocal() as db:
            query = db.query(Product).filter(Product.id == product_id)
            if user_id is not None:
                query = query.filter(Product.user_id == user_id)
            product = query.first()
            if product:
                for key, value in update_data.items():
                    setattr(product, key, value)
                db.commit()
                db.refresh(product)
                return self._to_dict(product)
            return None

    def bulk_update(self, product_ids: list[int], update_data: dict, user_id: int = None) -> int:
        """Массовое обновление товаров. Возвращает кол-во обновлённых строк."""
        if not product_ids or not update_data:
            return 0
        with SessionLocal() as db:
            query = db.query(Product).filter(Product.id.in_(product_ids))
            if user_id is not None:
                query = query.filter(Product.user_id == user_id)
            updated = query.update(update_data, synchronize_session=False)
            db.commit()
            return updated

    def update_batch(self, updates: list[tuple[int, dict]], user_id: int = None) -> int:
        """P-3: массовое обновление РАЗНЫМИ данными — одна сессия и один commit
        вместо сессии+commit на каждый товар (пакетная миграция)."""
        if not updates:
            return 0
        applied = 0
        with SessionLocal() as db:
            ids = [pid for pid, _ in updates]
            query = db.query(Product).filter(Product.id.in_(ids))
            if user_id is not None:
                query = query.filter(Product.user_id == user_id)
            by_id = {p.id: p for p in query.all()}
            for pid, data in updates:
                p = by_id.get(pid)
                if not p:
                    continue
                for key, value in data.items():
                    setattr(p, key, value)
                applied += 1
            db.commit()
        return applied

    def delete(self, product_id: int, user_id: int = None):
        """Удалить товар. Если указан user_id — проверяет владельца."""
        with SessionLocal() as db:
            query = db.query(Product).filter(Product.id == product_id)
            if user_id is not None:
                query = query.filter(Product.user_id == user_id)
            product = query.first()
            if product:
                db.delete(product)
                db.commit()
                return True
            return False
