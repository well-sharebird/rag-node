"""add permission_requests table

人工审批（HITL）完整闭环：敏感工具 require_approval 的审批请求持久化。

Revision ID: 016
Revises: 015
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 表可能已由 Base.metadata.create_all（应用启动）创建，需幂等
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'permission_requests' not in insp.get_table_names():
        op.create_table(
            'permission_requests',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('tool_name', sa.String(length=200), nullable=False),
            sa.Column('operation', sa.String(length=100), nullable=False, server_default='execute'),
            sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('permission_level', sa.String(length=30), nullable=False, server_default='approve_once'),
            sa.Column('risk_level', sa.String(length=20), nullable=False, server_default='medium'),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('requester_id', sa.Integer(), nullable=False),
            sa.Column('approver_id', sa.Integer(), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
    # 确保索引存在（create_all 不会建这些自定义索引）
    if 'ix_permission_requests_status_requester' not in [i['name'] for i in insp.get_indexes('permission_requests')]:
        op.create_index('ix_permission_requests_status_requester', 'permission_requests', ['status', 'requester_id'])
    if 'ix_permission_requests_created_at' not in [i['name'] for i in insp.get_indexes('permission_requests')]:
        op.create_index('ix_permission_requests_created_at', 'permission_requests', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_permission_requests_created_at', table_name='permission_requests')
    op.drop_index('ix_permission_requests_status_requester', table_name='permission_requests')
    op.drop_table('permission_requests')
