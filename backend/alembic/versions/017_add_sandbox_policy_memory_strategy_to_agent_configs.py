"""add sandbox_policy and memory_strategy to agent_configs

为子 Agent 补齐沙箱策略与记忆策略字段（Phase 3），
使子 Agent 配置可承载独立沙箱策略与记忆上下文策略。

Revision ID: 017
Revises: 016
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'agent_configs',
        sa.Column(
            'sandbox_policy',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        'agent_configs',
        sa.Column(
            'memory_strategy',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('agent_configs', 'memory_strategy')
    op.drop_column('agent_configs', 'sandbox_policy')
