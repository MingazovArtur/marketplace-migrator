"""
Настройка подключения к базе данных
Поддерживает PostgreSQL (production) и SQLite (development)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL

# Настройки подключения
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600
    )
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
