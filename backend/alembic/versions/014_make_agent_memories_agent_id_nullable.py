"""make agent_memories.agent_id nullable

checkpoint 记忆可能来自 meta / 虚拟代理（无 agent_configs 记录），
其 agent_id 无法满足 NOT NULL 外键约束。解除 NOT NULL 使断点持久化可用。

Revision ID: 014
Revises: 013
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 允许 agent_id 为 NULL（NULL 对外键 NO ACTION 默认放行）
    op.alter_column(
        'agent_memories',
        'agent_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'agent_memories',
        'agent_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
