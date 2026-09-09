from sqlalchemy.orm import Session
from database.models import Product
from database.session import SessionLocal, engine
from database.models import Base

# Создаем таблицы при старте, если их нет
Base.metadata.create_all(bind=engine)

class ProductRepository:
    def __init__(self):
        self._next_id = 1 # Для совместимости со старым кодом генерации ID

    def get_all(self):
        with SessionLocal() as db:
            products = db.query(Product).all()
            # Преобразуем SQLAlchemy объекты в словари для совместимости с Frontend
            return [
                {
                    "id": p.id, "name": p.name, "source": p.source,
                    "price": p.price, "status": p.status, "description": p.description,
                    "photos_count": p.photos_count, "category": p.category,
                    "mapped_category": p.mapped_category
                }
                for p in products
            ]

    def get_by_id(self, product_id: int):
        with SessionLocal() as db:
            p = db.query(Product).filter(Product.id == product_id).first()
            if not p:
                return None
            return {
                "id": p.id, "name": p.name, "source": p.source,
                "price": p.price, "status": p.status, "description": p.description,
                "photos_count": p.photos_count, "category": p.category,
                "mapped_category": p.mapped_category
            }

    def add(self, product_data):
        with SessionLocal() as db:
            # 1. Если передана Pydantic-модель, конвертируем её в словарь (Pydantic v2)
            if hasattr(product_data, "model_dump"):
                data_dict = product_data.model_dump()
            else:
                data_dict = product_data
            
            # 2. Убираем 'id', чтобы SQLAlchemy сама сгенерировала его (autoincrement)
            data_dict.pop("id", None)
            
            # 3. Создаем запись в БД
            new_product = Product(**data_dict)
            db.add(new_product)
            db.commit()
            db.refresh(new_product)
            
            self._next_id = max(self._next_id, new_product.id + 1)
            
            # 4. Возвращаем как словарь для совместимости с остальным кодом
            return {
                "id": new_product.id, 
                "name": new_product.name, 
                "source": new_product.source,
                "price": new_product.price, 
                "status": new_product.status, 
                "description": new_product.description, 
                "photos_count": new_product.photos_count,
                "category": new_product.category, 
                "mapped_category": new_product.mapped_category
            }

    def update(self, product_id: int, update_data: dict):
        with SessionLocal() as db:
            product = db.query(Product).filter(Product.id == product_id).first()
            if product:
                for key, value in update_data.items():
                    setattr(product, key, value)
                db.commit()
                db.refresh(product)
                return {
                    "id": product.id, "name": product.name, "source": product.source,
                    "price": product.price, "status": product.status, 
                    "description": product.description, "photos_count": product.photos_count,
                    "category": product.category, "mapped_category": product.mapped_category
                }
            return None

    def get_stats(self):
        with SessionLocal() as db:
            total = db.query(Product).count()
            pending = db.query(Product).filter(Product.status == "pending").count()
            success = db.query(Product).filter(Product.status == "success").count()
            error = db.query(Product).filter(Product.status == "error").count()
            processing = db.query(Product).filter(Product.status == "processing").count()
            
            return {
                "total": total, "pending": pending, "success": success, 
                "error": error, "processing": processing
            }

# Глобальный экземпляр
repo = ProductRepository()