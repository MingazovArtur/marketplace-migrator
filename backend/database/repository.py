"""
Репозиторий для работы с товарами в базе данных.
Все методы теперь принимают user_id для изоляции данных пользователей.
"""
from sqlalchemy.orm import Session
from database.models import Product
from database.session import SessionLocal, engine
from database.models import Base

# Создаем таблицы при старте, если их нет
Base.metadata.create_all(bind=engine)


class ProductRepository:
    def __init__(self):
        pass

    def get_all(self, user_id: int = None, is_admin: bool = False):
        """
        Получить все товары.
        - Если is_admin=True: возвращает все товары всех пользователей
        - Если user_id указан: возвращает только товары этого пользователя
        """
        with SessionLocal() as db:
            query = db.query(Product)
            
            # Если не админ и указан user_id — фильтруем
            if not is_admin and user_id is not None:
                query = query.filter(Product.user_id == user_id)
            
            products = query.all()
            return [
                {
                    "id": p.id, "name": p.name, "source": p.source,
                    "price": p.price, "status": p.status, "description": p.description,
                    "photos_count": p.photos_count, "category": p.category,
                    "mapped_category": p.mapped_category, "user_id": p.user_id
                }
                for p in products
            ]

    def get_by_id(self, product_id: int, user_id: int = None):
        """Получить товар по ID. Если указан user_id — проверяет владельца."""
        with SessionLocal() as db:
            query = db.query(Product).filter(Product.id == product_id)
            
            # Если передан user_id — добавляем проверку владельца
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
            # Если передана Pydantic-модель, конвертируем её в словарь
            if hasattr(product_data, "model_dump"):
                data_dict = product_data.model_dump()
            else:
                data_dict = product_data
            
            # Убираем 'id', чтобы SQLAlchemy сама сгенерировала его
            data_dict.pop("id", None)
            
            # Проверяем, что user_id присутствует
            if "user_id" not in data_dict or data_dict["user_id"] is None:
                raise ValueError("user_id обязателен при создании товара")
            
            # Создаем запись в БД
            new_product = Product(**data_dict)
            db.add(new_product)
            db.commit()
            db.refresh(new_product)
            
            # Возвращаем как словарь
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
            
            # Если передан user_id — добавляем проверку владельца
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
        """
        Получить статистику по товарам.
        - Если is_admin=True: статистика по всем товарам
        - Если user_id указан: статистика только по товарам этого пользователя
        """
        with SessionLocal() as db:
            query = db.query(Product)
            
            # Если не админ и указан user_id — фильтруем
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