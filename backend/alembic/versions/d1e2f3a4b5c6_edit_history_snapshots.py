"""edit history: bulk_edit_snapshots +action/label/undone (аудит-лог правок)
+ миграция_profiles (профили миграции)

Revision ID: d1e2f3a4b5c6
Revises: a9b1c2d3e4f5
Create Date: 2026-11-12 10:00:00.000000

Снапшоты правок становятся аудитом: у каждой операции появился тип (action),
человекочитаемое описание (label) и признак undone (операция отменена —
строка остаётся в истории, повторный undo запрещён).
Профили миграции: снимок «площадка + дефолты» для повторов в один клик.
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'a9b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'bulk_edit_snapshots',
        sa.Column('action', sa.String(length=40), nullable=False, server_default='bulk_update'),
    )
    op.add_column('bulk_edit_snapshots', sa.Column('label', sa.String(length=300), nullable=True))
    op.add_column(
        'bulk_edit_snapshots',
        sa.Column('undone', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        'migration_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('vat_rate', sa.String(), nullable=True),
        sa.Column('okpd_code', sa.String(), nullable=True),
        sa.Column('package_weight_grams', sa.Integer(), nullable=True),
        sa.Column('package_width_mm', sa.Integer(), nullable=True),
        sa.Column('package_height_mm', sa.Integer(), nullable=True),
        sa.Column('package_length_mm', sa.Integer(), nullable=True),
        sa.Column('brand', sa.String(), nullable=True),
        sa.Column('marking', sa.String(), nullable=True),
        sa.Column('price_default', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_migration_profile_user_name'),
    )
    op.create_index(op.f('ix_migration_profiles_id'), 'migration_profiles', ['id'], unique=False)
    op.create_index(
        op.f('ix_migration_profiles_user_id'), 'migration_profiles', ['user_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_migration_profiles_user_id'), table_name='migration_profiles')
    op.drop_index(op.f('ix_migration_profiles_id'), table_name='migration_profiles')
    op.drop_table('migration_profiles')
    op.drop_column('bulk_edit_snapshots', 'undone')
    op.drop_column('bulk_edit_snapshots', 'label')
    op.drop_column('bulk_edit_snapshots', 'action')
