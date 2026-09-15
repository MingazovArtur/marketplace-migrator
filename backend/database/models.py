"""
Модели базы данных SQLAlchemy
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с товарами
    products = relationship("Product", back_populates="owner")


class Category(Base):
    """Справочник категорий маркетплейсов"""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, nullable=False)  # 'ozon', 'wildberries', 'yandex'
    category_id = Column(String, nullable=False)  # ID категории в API площадки
    name = Column(String, nullable=False)  # Название категории
    parent_id = Column(String, nullable=True)  # ID родительской категории
    full_path = Column(String, nullable=True)  # Полный путь: "Электроника > Смартфоны"
    level = Column(Integer, default=0)  # Уровень вложенности (0, 1, 2...)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Индексы для быстрого поиска
    __table_args__ = (
        Index('idx_platform_category', 'platform', 'category_id'),
    )


class CategoryMapping(Base):
    """Маппинг категорий между площадками"""
    __tablename__ = "category_mappings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_platform = Column(String, nullable=False)  # 'ozon'
    source_category_id = Column(String, nullable=False)  # ID категории Ozon
    target_platform = Column(String, nullable=False)  # 'wildberries'
    target_category_id = Column(String, nullable=False)  # ID категории WB
    confidence = Column(Float, default=1.0)  # Уверенность маппинга (0-1)
    is_manual = Column(Boolean, default=False)  # Ручной маппинг или авто
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_mapping_lookup', 'source_platform', 'source_category_id', 'target_platform'),
    )


class Product(Base):
    """Модель товара"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Связь с пользователем
    
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String, default="pending")
    description = Column(String, default="")
    photos_count = Column(Integer, default=0)
    category = Column(String, default="Не указана")
    mapped_category = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Обратная связь
    owner = relationship("User", back_populates="products")