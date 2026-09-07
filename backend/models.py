from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "sqlite:///./migrator.db"  # Для продакшена: postgresql://...

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    products = relationship("Product", back_populates="user")
    marketplace_credentials = relationship("MarketplaceCredentials", back_populates="user")

class MarketplaceCredentials(Base):
    __tablename__ = "marketplace_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    marketplace = Column(String)  # "ozon", "wildberries", "yandex"
    api_key = Column(String)
    client_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    
    user = relationship("User", back_populates="marketplace_credentials")

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    source_marketplace = Column(String)
    
    # Основные данные
    external_id = Column(String)  # ID на исходном маркетплейсе
    name = Column(String)
    description = Column(String)
    price = Column(Integer)
    old_price = Column(Integer, nullable=True)
    quantity = Column(Integer)
    
    # Категории и характеристики
    category = Column(String)
    characteristics = Column(JSON)  # {"Цвет": "Красный", "Размер": "XL"}
    
    # Фотографии
    photos = Column(JSON)  # ["url1.jpg", "url2.jpg"]
    local_photo_paths = Column(JSON, nullable=True)  # ["photos/123/photo_1.jpg"]
    
    # Статус миграции
    migration_status = Column(String, default="pending")  # pending, processing, success, error
    target_marketplace = Column(String, nullable=True)
    target_external_id = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="products")

# Создаём таблицы
Base.metadata.create_all(bind=engine)