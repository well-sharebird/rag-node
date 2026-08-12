"""add security_policy to agent_configs

将 Manifest 的安全策略持久化到 AgentConfig，使 Harness 权限管控可使用。

Revision ID: 015
Revises: 014
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'agent_configs',
        sa.Column(
            'security_policy',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('agent_configs', 'security_policy')
