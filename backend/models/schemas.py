from pydantic import BaseModel
from typing import List, Optional

class Product(BaseModel):
    id: Optional[int] = None  # <-- СДЕЛАЛИ ОПЦИОНАЛЬНЫМ, чтобы репозиторий мог назначить его сам
    name: str
    source: str
    price: float
    status: str = "pending"
    description: Optional[str] = ""
    photos_count: int = 0
    category: Optional[str] = None
    mapped_category: Optional[str] = None

class ImportRequest(BaseModel):
    url: str
    auth_key: str

class MigrateRequest(BaseModel):
    product_id: int
    target_marketplace: str

class Stats(BaseModel):
    total: int
    pending: int
    success: int
    error: int
    processing: int