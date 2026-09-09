from typing import List, Optional
from models.schemas import Product, Stats

class InMemoryRepository:
    def __init__(self):
        self._db: List[Product] = [
            Product(id=1, name="Швабра с отжимом, 10л", source="Ozon (тест)", price=899, status="pending", photos_count=23, category="Дом и сад"),
            Product(id=2, name="Набор пластиковых мисок", source="Ozon (тест)", price=450, status="success", photos_count=16, category="Посуда"),
        ]
        self._next_id = 3

    def get_all(self) -> List[Product]:
        return self._db

    def get_by_id(self, product_id: int) -> Optional[Product]:
        return next((p for p in self._db if p.id == product_id), None)

    def add(self, product: Product) -> Product:
        product.id = self._next_id
        self._db.append(product)
        self._next_id += 1
        return product

    def update(self, product_id: int, update_data: dict) -> Optional[Product]:
        product = self.get_by_id(product_id)
        if product:
            for key, value in update_data.items():
                setattr(product, key, value)
        return product

    def delete(self, product_id: int) -> bool:
        initial_len = len(self._db)
        self._db = [p for p in self._db if p.id != product_id]
        return len(self._db) < initial_len

    def get_stats(self) -> Stats:
        total = len(self._db)
        return Stats(
            total=total,
            pending=sum(1 for p in self._db if p.status == "pending"),
            success=sum(1 for p in self._db if p.status == "success"),
            error=sum(1 for p in self._db if p.status == "error"),
            processing=sum(1 for p in self._db if p.status == "processing")
        )

# Глобальный экземпляр (в будущем заменим на зависимость от БД)
repo = InMemoryRepository()