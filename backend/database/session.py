"""
Настройка подключения к базе данных
Поддерживает PostgreSQL (production) и SQLite (development)
Добавлен неблокирующий контур AsyncSession + asyncpg (Dual-Engine)
без поломки синхронных задач Celery и legacy-сервисов.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL

# ==================== 1. Синхронный контур (Celery, миграции, repo) ====================

if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600
    )
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Синхронный Dependency для получения сессии БД (обратная совместимость)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== 2. Асинхронный контур (FastAPI + asyncpg / aiosqlite) ====================


def _make_async_url(url: str) -> str:
    """Преобразует синхронный DATABASE_URL в URL для асинхронного драйвера."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


ASYNC_DATABASE_URL = _make_async_url(DATABASE_URL)

if ASYNC_DATABASE_URL.startswith("postgresql+asyncpg"):
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
else:
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронный Dependency для получения неблокирующей сессии БД (AsyncSession)"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
