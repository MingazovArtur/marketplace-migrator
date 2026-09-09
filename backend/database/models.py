from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String, default="pending")
    description = Column(String, default="")
    photos_count = Column(Integer, default=0)
    category = Column(String, default="Не указана")
    mapped_category = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)