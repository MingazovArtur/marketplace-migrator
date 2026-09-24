"""make platform_category_specs global

Revision ID: 5935606
"""
from alembic import op

revision = "xxxx"
down_revision = "9cfd236a7340"   # ← последний revision вашей цепи
branch_labels = None
depends_on = None


def upgrade():
    # 1) Дедупликация: оставляем самую свежую строку на (platform, category_id)
    op.execute("""
        DELETE FROM platform_category_specs a
        USING platform_category_specs b
        WHERE a.platform = b.platform
          AND a.category_id = b.category_id
          AND a.fetched_at < b.fetched_at
    """)
    op.execute("""
        DELETE FROM platform_category_specs a
        USING platform_category_specs b
        WHERE a.platform = b.platform
          AND a.category_id = b.category_id
          AND a.id < b.id
    """)
    # 2) Старый уникальный ключ долой
    op.drop_constraint("uq_user_platform_category", "platform_category_specs", type_="unique")
    # 3) user_id nullable (аудит)
    op.alter_column("platform_category_specs", "user_id", nullable=True)
    # 4) Новая уникальность: одна строка на категорию площадки
    op.create_unique_constraint("uq_platform_category", "platform_category_specs",
                                ["platform", "category_id"])


def downgrade():
    op.drop_constraint("uq_platform_category", "platform_category_specs", type_="unique")
    op.alter_column("platform_category_specs", "user_id", nullable=False)
    op.create_unique_constraint("uq_user_platform_category", "platform_category_specs",
                                ["user_id", "platform", "category_id"])