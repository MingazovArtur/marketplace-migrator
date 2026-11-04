"""Репозиторий характеристик товаров."""

from database.models import Product, ProductAttribute
from database.repository.products import ProductRepository
from database.session import SessionLocal


class AttributeRepository:
    """Репозиторий характеристик товаров"""

    @staticmethod
    def _to_dict(attr) -> dict:
        return {
            "id": attr.id,
            "product_id": attr.product_id,
            "name": attr.name,
            "value": attr.value,
            "platform_attribute_id": attr.platform_attribute_id,
            "sort_order": attr.sort_order,
        }

    def get_by_product(self, product_id: int) -> list[dict]:
        """Получить все характеристики товара"""
        with SessionLocal() as db:
            attrs = (
                db.query(ProductAttribute)
                .filter(ProductAttribute.product_id == product_id)
                .order_by(ProductAttribute.sort_order)
                .all()
            )
            return [self._to_dict(a) for a in attrs]

    def set_attributes(self, product_id: int, attributes: list[dict]) -> list[dict]:
        """
        Заменить все характеристики товара на новые.
        Используется при импорте и массовом редактировании.
        """
        with SessionLocal() as db:
            # Удаляем старые
            db.query(ProductAttribute).filter(ProductAttribute.product_id == product_id).delete()

            # Создаём новые (P-2: add_all + один flush вместо add+flush на строку)
            rows = ProductRepository._attr_rows(product_id, attributes)
            if rows:
                db.add_all(rows)
                db.flush()
            db.commit()
            return [self._to_dict(a) for a in rows]

    def add_attribute(
        self, product_id: int, name: str, value: str, platform_attribute_id: str = None
    ) -> dict:
        """Добавить одну характеристику"""
        with SessionLocal() as db:
            max_order = (
                db.query(ProductAttribute.sort_order)
                .filter(ProductAttribute.product_id == product_id)
                .order_by(ProductAttribute.sort_order.desc())
                .first()
            )
            next_order = (max_order[0] or 0) + 1 if max_order else 0

            new_attr = ProductAttribute(
                product_id=product_id,
                name=str(name).strip(),
                value=str(value).strip(),
                platform_attribute_id=platform_attribute_id,
                sort_order=next_order,
            )
            db.add(new_attr)
            db.commit()
            db.refresh(new_attr)
            return self._to_dict(new_attr)

    def delete_attribute(self, attribute_id: int, user_id: int = None) -> bool:
        """Удалить характеристику (с проверкой владельца товара)"""
        with SessionLocal() as db:
            attr = db.query(ProductAttribute).filter(ProductAttribute.id == attribute_id).first()
            if not attr:
                return False
            if user_id is not None:
                product = db.query(Product).filter(Product.id == attr.product_id).first()
                if not product or product.user_id != user_id:
                    return False
            db.delete(attr)
            db.commit()
            return True


# Глобальный экземпляр (совместимость импортов: from database.repository import attr_repo)
attr_repo = AttributeRepository()
