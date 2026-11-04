"""P-1 (неделя 3): денежные поля FLOAT -> NUMERIC(12,2)

Товары, варианты, журнал миграций. Postgres: ALTER ... USING price::numeric(12,2)
(SQLite в разработке не умеет USING — там тип не меняем, batch не нужен:
SQLite хранит всё как REAL/NUMERIC и caste'ы не теряет в прод-сценариях).

Revision ID: c3e5f7a9b1d2
Revises: e042bc4e1548
Create Date: 2025-11-05
"""

import logging

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision = "c3e5f7a9b1d2"
down_revision = "e042bc4e1548"
branch_labels = None
depends_on = None

# (таблица, колонка) — все денежные поля из ревью P-1
MONEY_COLUMNS = [
    ("products", "price"),
    ("product_variants", "price"),
    ("migration_logs", "old_price"),
    ("migration_logs", "new_price"),
]


def _column_is_numeric(insp, table: str, column: str) -> bool:
    """True, если колонка уже numeric (защита от повторного применения)."""
    try:
        for c in insp.get_columns(table):
            if c["name"] == column:
                return isinstance(c["type"], (sa.Numeric, sa.DECIMAL))
    except Exception:
        pass
    return False


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect != "postgresql":
        # SQLite (разработка): значения и так хранятся гибко;
        # ALTER TYPE не поддерживается, прод- БД — только Postgres.
        logger.info(
            "P-1: dialect=%s — денежные колонки оставлены как есть "
            "(NUMERIC-миграция применяется только на PostgreSQL)", dialect,
        )
        return

    insp = sa.inspect(bind)
    for table, column in MONEY_COLUMNS:
        # не дублируем, если уже numeric (например, база восстановлена из pg_dump)
        try:
            cols = {c["name"] for c in insp.get_columns(table)}
            if column not in cols:
                logger.warning("P-1: %s.%s не найдена — пропускаю", table, column)
                continue
            if _column_is_numeric(insp, table, column):
                logger.info("P-1: %s.%s уже numeric — пропускаю", table, column)
                continue
        except Exception:
            pass

        logger.info("P-1: %s.%s FLOAT -> NUMERIC(12,2)", table, column)
        op.alter_column(
            table,
            column,
            existing_type=sa.Float(),
            type_=sa.Numeric(12, 2),
            postgresql_using=f"{column}::numeric(12,2)",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    insp = sa.inspect(bind)
    for table, column in MONEY_COLUMNS:
        try:
            cols = {c["name"] for c in insp.get_columns(table)}
            if column not in cols or not _column_is_numeric(insp, table, column):
                continue
        except Exception:
            pass
        op.alter_column(
            table,
            column,
            existing_type=sa.Numeric(12, 2),
            type_=sa.Float(),
            postgresql_using=f"{column}::double precision",
        )
