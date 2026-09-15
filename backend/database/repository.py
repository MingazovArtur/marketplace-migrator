"""
Репозиторий для работы с товарами в базе данных.
Поддерживает фильтрацию, сортировку и пагинацию.
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from database.models import Product
from database.session import SessionLocal, engine
from database.models import Base
from typing import Optional, List, Dict

# Создаем таблицы при старте, если их нет
Base.metadata.create_all(bind=engine)


class ProductRepository:
    def __init__(self):
        pass

    def get_all(
        self, 
        user_id: int = None, 
        is_admin: bool = False,
        search: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50
    ):
        """
        Получить товары с фильтрацией, сортировкой и пагинацией.
        """
        with SessionLocal() as db:
            query = db.query(Product)
            
            # Фильтрация по пользователю
            if not is_admin and user_id is not None:
                query = query.filter(Product.user_id == user_id)
            
            # Поиск по названию
            if search:
                query = query.filter(Product.name.ilike(f"%{search}%"))
            
            # Фильтр по статусу
            if status:
                query = query.filter(Product.status == status)
            
            # Фильтр по источнику
            if source:
                query = query.filter(Product.source.ilike(f"%{source}%"))
            
            # Сортировка
            sort_column = getattr(Product, sort_by, Product.created_at)
            if sort_order == "asc":
                query = query.order_by(asc(sort_column))
            else:
                query = query.order_by(desc(sort_column))
            
            # Пагинация
            products = query.offset(skip).limit(limit).all()
            
            # Получаем общее количество для пагинации
            total_query = db.query(Product)
            if not is_admin and user_id is not None:
                total_query = total_query.filter(Product.user_id == user_id)
            if search:
                total_query = total_query.filter(Product.name.ilike(f"%{search}%"))
            if status:
                total_query = total_query.filter(Product.status == status)
            if source:
                total_query = total_query.filter(Product.source.ilike(f"%{source}%"))
            total = total_query.count()
            
            return {
                "total": total,
                "products": [
                    {
                        "id": p.id, "name": p.name, "source": p.source,
                        "price": p.price, "status": p.status, "description": p.description,
                        "photos_count": p.photos_count, "category": p.category,
                        "mapped_category": p.mapped_category, "user_id": p.user_id,
                        "created_at": p.created_at.isoformat() if p.created_at else None
                    }
                    for p in products
                ]
            }

    def get_by_id(self, product_id: int, user_id: int = None):
        """Получить товар по ID. Если указан user_id — проверяет владельца."""
        with SessionLocal() as db:
            query = db.query(Product).filter(Product.id == product_id)
            
            if user_id is not None:
                query = query.filter(Product.user_id == user_id)
            
            p = query.first()
            if not p:
                return None
            return {
                "id": p.id, "name": p.name, "source": p.source,
                "price": p.price, "status": p.status, "description": p.description,
                "photos_count": p.photos_count, "category": p.category,
                "mapped_category": p.mapped_category, "user_id": p.user_id
            }

    def add(self, product_data):
        """Добавить новый товар. product_data должен содержать user_id."""
        with SessionLocal() as db:
            if hasattr(product_data, "model_dump"):
                data_dict = product_data.model_dump()
            else:
                data_dict = product_data
            
            data_dict.pop("id", None)
            
            if "user_id" not in data_dict or data_dict["user_id"] is None:
                raise ValueError("user_id обязателен при создании товара")
            
            new_product = Product(**data_dict)
            db.add(new_product)
            db.commit()
            db.refresh(new_product)
            
            return {
                "id": new_product.id, 
                "name": new_product.name, 
                "source": new_product.source,
                "price": new_product.price, 
                "status": new_product.status, 
                "description": new_product.description, 
                "photos_count": new_product.photos_count,
                "category": new_product.category, 
                "mapped_category": new_product.mapped_category,
                "user_id": new_product.user_id
            }

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
                return {
                    "id": product.id, "name": product.name, "source": product.source,
                    "price": product.price, "status": product.status, 
                    "description": product.description, "photos_count": product.photos_count,
                    "category": product.category, "mapped_category": product.mapped_category,
                    "user_id": product.user_id
                }
            return None

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

    def get_stats(self, user_id: int = None, is_admin: bool = False):
        """Получить статистику по товарам."""
        with SessionLocal() as db:
            query = db.query(Product)
            
            if not is_admin and user_id is not None:
                query = query.filter(Product.user_id == user_id)
            
            total = query.count()
            pending = query.filter(Product.status == "pending").count()
            success = query.filter(Product.status == "success").count()
            error = query.filter(Product.status == "error").count()
            processing = query.filter(Product.status == "processing").count()
            
            return {
                "total": total, "pending": pending, "success": success, 
                "error": error, "processing": processing
            }


# Глобальный экземпляр
repo = ProductRepository()