"""fix_model_unique_constraint

Revision ID: 004
Revises: 003
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 删除旧的唯一约束 (model_type, name)
    op.drop_constraint('uq_model_type_name', 'model_configs', type_='unique')

    # 创建新的唯一约束 (model_type, provider, name)
    # 这样同一供应商下不能有同名模型，但不同供应商下可以有同名模型
    op.create_unique_constraint(
        'uq_model_type_provider_name',
        'model_configs',
        ['model_type', 'provider', 'name']
    )


def downgrade() -> None:
    # 恢复旧的约束
    op.drop_constraint('uq_model_type_provider_name', 'model_configs', type_='unique')
    op.create_unique_constraint(
        'uq_model_type_name',
        'model_configs',
        ['model_type', 'name']
    )
