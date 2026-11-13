"""batch email notifications: users +notify_batch_done

Revision ID: f3b4c5d6e7f8
Revises: e2f3a4b5c6d7
Create Date: 2026-11-12 12:00:00.000000

Переключатель «писать письмо о завершении пакетной миграции»
(включён по умолчанию; отключается в меню профиля).
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'f3b4c5d6e7f8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('notify_batch_done', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('users', 'notify_batch_done')
