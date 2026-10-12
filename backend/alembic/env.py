"""
Alembic environment configuration
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Импортируем модели (все классы регистрируются в Base.metadata)
from core.config import DATABASE_URL
from database.models import Base

# Alembic Config object
config = context.config

# Override sqlalchemy.url из переменной окружения
# ✅ Экранируем '%' — иначе ConfigParser падает на паролях с '%'
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata

# ✅ Страховка: если модели не загрузились — падаем сразу, а не генерим пустую миграцию
if not target_metadata.tables:
    raise RuntimeError(
        "Base.metadata пуст! Проверьте импорты моделей в database/models.py "
        "(или добавьте недостающие импорты в alembic/env.py)."
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # ✅ те же флаги сравнения, что и в online
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # ✅ замечать смену типов колонок
            compare_server_default=True,  # ✅ замечать смену default-значений
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
