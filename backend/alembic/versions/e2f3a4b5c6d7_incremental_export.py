"""incremental export: products +last_export_at/last_export_platform

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-11-12 11:00:00.000000

Инкрементальный экспорт: фиксируем, когда и на какую площадку товар
выгружался в последний раз. Фильтр «только изменённые»:
updated_at > last_export_at либо товар ещё не выгружался.
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('last_export_at', sa.DateTime(), nullable=True))
    op.add_column('products', sa.Column('last_export_platform', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'last_export_platform')
    op.drop_column('products', 'last_export_at')
