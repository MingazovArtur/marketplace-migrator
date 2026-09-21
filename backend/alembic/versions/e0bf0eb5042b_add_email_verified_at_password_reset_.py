"""add email_verified_at + password_reset_tokens

Revision ID: e0bf0eb5042b
Revises: f862db70d068
Create Date: 2026-09-21 09:01:16.216631

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'e0bf0eb5042b'
down_revision: Union[str, None] = 'f862db70d068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Идемпотентная миграция: проверяет существование объектов перед созданием.
    Это нужно, т.к. колонка email_verified_at и таблица password_reset_tokens
    уже физически существуют в БД (созданы ранее), но история Alembic их не знает.
    """
    conn = op.get_bind()

    # 1. Поле email_verified_at — добавляем, только если его ещё нет
    has_col = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'email_verified_at'
        )
    """)).scalar()
    if not has_col:
        op.add_column('users', sa.Column('email_verified_at', sa.DateTime(), nullable=True))

    # 2. Таблица password_reset_tokens — создаём, только если её ещё нет
    has_table = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'password_reset_tokens'
        )
    """)).scalar()
    if not has_table:
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
        op.create_index('ix_password_reset_tokens_user_id', 'password_reset_tokens', ['user_id'])
        op.create_index('ix_password_reset_tokens_token_hash', 'password_reset_tokens', ['token_hash'])
    else:
        # Таблица есть — создаём недостающие индексы (если их нет)
        for idx_name, col in [
            ('ix_password_reset_tokens_id', 'id'),
            ('ix_password_reset_tokens_user_id', 'user_id'),
            ('ix_password_reset_tokens_token_hash', 'token_hash'),
        ]:
            has_idx = conn.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes WHERE indexname = '{idx_name}'
                )
            """)).scalar()
            if not has_idx:
                op.create_index(idx_name, 'password_reset_tokens', [col])


def downgrade() -> None:
    """Обратная миграция (с проверками — идемпотентная)."""
    conn = op.get_bind()

    has_table = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'password_reset_tokens'
        )
    """)).scalar()

    if has_table:
        for idx in ('ix_password_reset_tokens_token_hash', 'ix_password_reset_tokens_user_id', 'ix_password_reset_tokens_id'):
            has_idx = conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = '{idx}')")).scalar()
            if has_idx:
                op.drop_index(idx, table_name='password_reset_tokens')
        op.drop_table('password_reset_tokens')

    has_col = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'email_verified_at'
        )
    """)).scalar()
    if has_col:
        op.drop_column('users', 'email_verified_at')