"""add email_verified_at + password_reset_tokens

Revision ID: f862db70d068
Revises: 732524b492fc
Create Date: 2026-09-21 08:10:06.158158

Идемпотентная миграция (R-35): объединяет исходную f862db70d068 и её
дубликат e0bf0eb5042b, висевший следующим звеном цепочки с тем же описанием.
Колонка и таблица создаются только при отсутствии — безопасно и для БД,
где они уже существуют физически, но история Alembic о них не знает.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f862db70d068'
down_revision: str | None = '732524b492fc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _exists(conn, sql: str) -> bool:
    """SELECT EXISTS(...) → bool."""
    return bool(conn.execute(text(sql)).scalar())


def upgrade() -> None:
    conn = op.get_bind()

    # 1. users.email_verified_at — только если колонки ещё нет
    if not _exists(conn, """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'email_verified_at'
        )
    """):
        op.add_column('users', sa.Column('email_verified_at', sa.DateTime(), nullable=True))

    # 2. password_reset_tokens — только если таблицы ещё нет.
    #    Схема повторяет модель PasswordResetToken: UNIQUE-констрейнты
    #    user_id/token_hash + единственный модельный индекс ix_…_id
    #    (отдельные индексы по user_id/token_hash в модели НЕ объявлены —
    #    R-35: раньше их создавала миграция-дубликат, а следующая же
    #    миграция 6de484… дропала как несоответствующие модели).
    if not _exists(conn, """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'password_reset_tokens'
        )
    """):
        op.create_table(
            'password_reset_tokens',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('token_hash', sa.String(length=64), nullable=False, unique=True),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        )
        op.create_index('ix_password_reset_tokens_id', 'password_reset_tokens', ['id'])
    elif not _exists(conn, """
        SELECT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE indexname = 'ix_password_reset_tokens_id'
        )
    """):
        # таблица существует вне истории (например, создана create_all) —
        # досоздаём только модельный индекс по id
        op.create_index('ix_password_reset_tokens_id', 'password_reset_tokens', ['id'])


def downgrade() -> None:
    """Обратная миграция (идемпотентная — на случай частично изменённой БД)."""
    conn = op.get_bind()

    if _exists(conn, """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'password_reset_tokens'
        )
    """):
        op.drop_table('password_reset_tokens')

    if _exists(conn, """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'email_verified_at'
        )
    """):
        op.drop_column('users', 'email_verified_at')
