"""add export_defaults table

Revision ID: e8f1a2b3c4d5
Revises: 732524b492fc
Create Date: 2026-09-25
"""
import sqlalchemy as sa

from alembic import op

revision = "e8f1a2b3c4d5"
down_revision = "9cfd236a7340"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_defaults",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_name", sa.String(length=255), nullable=True),
        sa.Column("vat_rate", sa.String(length=16), nullable=True),
        sa.Column("okpd_code", sa.String(length=64), nullable=True),
        sa.Column("package_weight_grams", sa.Integer(), nullable=True),
        sa.Column("package_width_mm", sa.Integer(), nullable=True),
        sa.Column("package_height_mm", sa.Integer(), nullable=True),
        sa.Column("package_length_mm", sa.Integer(), nullable=True),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("marking", sa.String(length=16), nullable=True, server_default="Нет"),
    )
    op.create_unique_constraint("uq_export_defaults_user_category", "export_defaults", ["user_id", "category_name"])
    op.create_index("ix_export_defaults_user_id", "export_defaults", ["user_id"])
    op.create_index("ix_export_defaults_user_category", "export_defaults", ["user_id", "category_name"])


def downgrade() -> None:
    op.drop_index("ix_export_defaults_user_category", table_name="export_defaults")
    op.drop_index("ix_export_defaults_user_id", table_name="export_defaults")
    op.drop_constraint("uq_export_defaults_user_category", "export_defaults", type_="unique")
    op.drop_table("export_defaults")
