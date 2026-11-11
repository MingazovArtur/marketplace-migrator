"""add bulk_edit_snapshots (undo для массового обновления)

Revision ID: a9b1c2d3e4f5
Revises: c3e5f7a9b1d2
Create Date: 2026-11-11 16:00:00.000000

Хранит до 5 последних снапшотов на пользователя: прежние цена/бренд/
категория назначения каждого затронутого товара. POST /api/products/bulk-undo
восстанавливает значения из последнего снапшота.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a9b1c2d3e4f5'
down_revision = 'c3e5f7a9b1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bulk_edit_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bulk_edit_snapshots_id'), 'bulk_edit_snapshots', ['id'], unique=False)
    op.create_index(
        op.f('ix_bulk_edit_snapshots_user_id'), 'bulk_edit_snapshots', ['user_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_bulk_edit_snapshots_user_id'), table_name='bulk_edit_snapshots')
    op.drop_index(op.f('ix_bulk_edit_snapshots_id'), table_name='bulk_edit_snapshots')
    op.drop_table('bulk_edit_snapshots')
