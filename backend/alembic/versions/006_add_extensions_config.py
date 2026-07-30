"""add extensions_config to agent_configs

Revision ID: 006_add_extensions_config
Revises: 005_add_agent_tables
Create Date: 2026-07-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加 extensions_config 字段"""
    op.add_column(
        'agent_configs',
        sa.Column(
            'extensions_config',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            default=sa.text("'{}'::jsonb"),
            comment="扩展配置 - 用于 LangGraph 工厂模式动态构建"
        )
    )

    # 为现有记录设置默认值
    op.execute("""
        UPDATE agent_configs
        SET extensions_config = '{}'::jsonb
        WHERE extensions_config IS NULL
    """)


def downgrade() -> None:
    """回滚：删除 extensions_config 字段"""
    op.drop_column('agent_configs', 'extensions_config')
