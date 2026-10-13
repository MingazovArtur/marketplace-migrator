"""add indexes for performance

Revision ID: a1b2c3d4e5f6
Revises: b1c2d3e4f5a6
Create Date: 2026-10-12 12:00:00.000000
"""
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_products_user_id', 'products', ['user_id'], if_not_exists=True)
    op.create_index('ix_products_status', 'products', ['status'], if_not_exists=True)
    op.create_index('ix_products_source', 'products', ['source'], if_not_exists=True)
    op.create_index('ix_products_sku', 'products', ['sku'], if_not_exists=True)
    op.create_index('ix_products_external_id', 'products', ['external_id'], if_not_exists=True)
    op.create_index('ix_products_category', 'products', ['category'], if_not_exists=True)
    op.create_index('ix_products_created_at', 'products', ['created_at'], if_not_exists=True)
    op.create_index('ix_products_user_status_created', 'products', ['user_id', 'status', 'created_at'], if_not_exists=True)
    op.create_index('ix_platform_category_specs_platform', 'platform_category_specs', ['platform'], if_not_exists=True)
    op.create_index('ix_platform_category_specs_category_id', 'platform_category_specs', ['category_id'], if_not_exists=True)
    op.create_index('ix_platform_category_specs_platform_category', 'platform_category_specs', ['platform', 'category_id'], unique=True, if_not_exists=True)
    op.create_index('ix_category_mapping_user_id', 'category_mappings', ['user_id'], if_not_exists=True)
    op.create_index('ix_category_mapping_source', 'category_mappings', ['source_platform', 'source_category_id'], if_not_exists=True)
    op.create_index('ix_file_operation_logs_user_id', 'file_operation_logs', ['user_id'], if_not_exists=True)
    op.create_index('ix_file_operation_logs_created_at', 'file_operation_logs', ['created_at'], if_not_exists=True)
    op.create_index('ix_file_operation_logs_user_created', 'file_operation_logs', ['user_id', 'created_at'], if_not_exists=True)
    op.create_index('ix_migration_logs_user_id', 'migration_logs', ['user_id'], if_not_exists=True)
    op.create_index('ix_migration_logs_created_at', 'migration_logs', ['created_at'], if_not_exists=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True, if_not_exists=True)
    op.create_index('ix_users_username', 'users', ['username'], unique=True, if_not_exists=True)


def downgrade() -> None:
    op.drop_index('ix_users_username', table_name='users')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_migration_logs_created_at', table_name='migration_logs')
    op.drop_index('ix_migration_logs_user_id', table_name='migration_logs')
    op.drop_index('ix_file_operation_logs_user_created', table_name='file_operation_logs')
    op.drop_index('ix_file_operation_logs_created_at', table_name='file_operation_logs')
    op.drop_index('ix_file_operation_logs_user_id', table_name='file_operation_logs')
    op.drop_index('ix_category_mapping_source', table_name='category_mappings')
    op.drop_index('ix_category_mapping_user_id', table_name='category_mappings')
    op.drop_index('ix_platform_category_specs_platform_category', table_name='platform_category_specs')
    op.drop_index('ix_platform_category_specs_category_id', table_name='platform_category_specs')
    op.drop_index('ix_platform_category_specs_platform', table_name='platform_category_specs')
    op.drop_index('ix_products_user_status_created', table_name='products')
    op.drop_index('ix_products_created_at', table_name='products')
    op.drop_index('ix_products_category', table_name='products')
    op.drop_index('ix_products_external_id', table_name='products')
    op.drop_index('ix_products_sku', table_name='products')
    op.drop_index('ix_products_source', table_name='products')
    op.drop_index('ix_products_status', table_name='products')
    op.drop_index('ix_products_user_id', table_name='products')