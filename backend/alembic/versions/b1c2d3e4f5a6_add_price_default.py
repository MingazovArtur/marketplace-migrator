"""add price_default to export_defaults

Revision ID: b1c2d3e4f5a6
Revises: e8f1a2b3c4d5
"""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "e8f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "export_defaults",
        sa.Column("price_default", sa.Numeric(precision=10, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("export_defaults", "price_default")