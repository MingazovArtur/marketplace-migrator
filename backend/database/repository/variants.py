"""Репозиторий вариаций товаров."""

from database.models import Product, ProductVariant
from database.repository.products import ProductRepository
from database.session import SessionLocal


class VariantRepository:
    """Репозиторий вариаций товаров"""

    @staticmethod
    def _to_dict(v) -> dict:
        return {
            "id": v.id,
            "product_id": v.product_id,
            "sku": v.sku,
            "size": v.size,
            "color": v.color,
            # P-1: Decimal -> float
            "price": float(v.price) if v.price is not None else None,
            "stock": v.stock,
            "external_id": v.external_id,
            "sort_order": v.sort_order,
        }

    def get_by_product(self, product_id: int) -> list[dict]:
        with SessionLocal() as db:
            variants = (
                db.query(ProductVariant)
                .filter(ProductVariant.product_id == product_id)
                .order_by(ProductVariant.sort_order)
                .all()
            )
            return [self._to_dict(v) for v in variants]

    def set_variants(self, product_id: int, variants: list[dict]) -> list[dict]:
        """Полностью заменить набор вариаций товара"""
        with SessionLocal() as db:
            db.query(ProductVariant).filter(ProductVariant.product_id == product_id).delete()

            # P-2: add_all + один flush вместо add+flush на строку
            rows = ProductRepository._variant_rows(product_id, variants)
            if rows:
                db.add_all(rows)
                db.flush()
            db.commit()
            return [self._to_dict(v) for v in rows]

    def delete_variant(self, variant_id: int, user_id: int = None) -> bool:
        with SessionLocal() as db:
            v = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
            if not v:
                return False
            if user_id is not None:
                product = db.query(Product).filter(Product.id == v.product_id).first()
                if not product or product.user_id != user_id:
                    return False
            db.delete(v)
            db.commit()
            return True


# Глобальный экземпляр (совместимость импортов: from database.repository import variant_repo)
variant_repo = VariantRepository()
