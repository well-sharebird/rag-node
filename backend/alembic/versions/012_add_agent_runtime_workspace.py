"""add agent runtime workspace session tables

Revision ID: 012
Revises: 011
Create Date: 2026-08-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ================================================================
    # 1. Workspace 工作区表 (最先创建，被其他表引用)
    # ================================================================
    op.create_table(
        'workspaces',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('root_path', sa.String(length=500), nullable=False),
        sa.Column('storage_quota_bytes', sa.BigInteger(), nullable=False, default=10737418240),
        sa.Column('storage_used_bytes', sa.BigInteger(), nullable=False, default=0),
        sa.Column('status', sa.String(length=20), nullable=False, default='active'),
        sa.Column('is_isolated', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_workspace_user_tenant', 'workspaces', ['user_id', 'tenant_id'])
    op.create_index('idx_workspace_status', 'workspaces', ['status'])
    op.create_index('ix_workspaces_root_path', 'workspaces', ['root_path'], unique=True)

    # ================================================================
    # 2. AgentRuntime 运行时表 (在 workspace_audit_logs 之前创建)
    # ================================================================
    op.create_table(
        'agent_runtimes',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('manifest', postgresql.JSONB(astext_type=sa.Text()), nullable=False, default={}),
        sa.Column('sandbox_type', sa.String(length=20), nullable=False, default='nsjail'),
        sa.Column('sandbox_id', sa.String(length=200), nullable=True),
        sa.Column('sandbox_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, default='initializing'),
        sa.Column('resource_usage', postgresql.JSONB(astext_type=sa.Text()), nullable=False, default={}),
        sa.Column('last_active_at', sa.DateTime(), nullable=True),
        sa.Column('idle_timeout_seconds', sa.Integer(), nullable=False, default=900),
        sa.Column('auto_sleep_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('start_count', sa.Integer(), nullable=False, default=0),
        sa.Column('last_started_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('stopped_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['agent_id'], ['agent_configs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_runtime_agent_status', 'agent_runtimes', ['agent_id', 'status'])
    op.create_index('idx_runtime_workspace_status', 'agent_runtimes', ['workspace_id', 'status'])
    op.create_index('idx_runtime_sandbox', 'agent_runtimes', ['sandbox_id'])
    op.create_index('idx_runtime_last_active', 'agent_runtimes', ['last_active_at'])

    # ================================================================
    # 3. WorkspaceAuditLog 工作区审计日志表 (在 agent_runtimes 之后)
    # ================================================================
    op.create_table(
        'workspace_audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('workspace_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('runtime_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(length=100), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, default=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['runtime_id'], ['agent_runtimes.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_audit_workspace_action', 'workspace_audit_logs', ['workspace_id', 'action'])
    op.create_index('idx_audit_workspace_created', 'workspace_audit_logs', ['workspace_id', 'created_at'])
    op.create_index('idx_audit_user_created', 'workspace_audit_logs', ['user_id', 'created_at'])

    # ================================================================
    # 4. WorkspaceFile 工作区文件表
    # ================================================================
    op.create_table(
        'workspace_files',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('runtime_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(length=100), nullable=True),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('relative_path', sa.String(length=1000), nullable=False),
        sa.Column('absolute_path', sa.String(length=1000), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('mime_type', sa.String(length=200), nullable=True),
        sa.Column('file_hash', sa.String(length=64), nullable=True),
        sa.Column('source_type', sa.String(length=20), nullable=False, default='upload'),
        sa.Column('is_sandbox_generated', sa.Boolean(), nullable=False, default=False),
        sa.Column('scan_status', sa.String(length=20), nullable=False, default='pending'),
        sa.Column('scan_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'relative_path', name='uq_workspace_file_path'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['runtime_id'], ['agent_runtimes.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_file_workspace_created', 'workspace_files', ['workspace_id', 'created_at'])
    op.create_index('idx_file_scan_status', 'workspace_files', ['scan_status'])
    op.create_index('ix_workspace_files_session_id', 'workspace_files', ['session_id'])

    # ================================================================
    # 5. AgentRuntimeEvent 运行时事件表
    # ================================================================
    op.create_table(
        'agent_runtime_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('runtime_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('event_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['runtime_id'], ['agent_runtimes.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_event_runtime_created', 'agent_runtime_events', ['runtime_id', 'created_at'])
    op.create_index('idx_event_type_created', 'agent_runtime_events', ['event_type', 'created_at'])

    # ================================================================
    # 6. AgentSession 会话表
    # ================================================================
    op.create_table(
        'agent_sessions',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('runtime_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_token_hash', sa.String(length=64), nullable=False),
        sa.Column('session_token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('context_window_tokens', sa.Integer(), nullable=False, default=4096),
        sa.Column('context_used_tokens', sa.Integer(), nullable=False, default=0),
        sa.Column('status', sa.String(length=20), nullable=False, default='active'),
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['runtime_id'], ['agent_runtimes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_session_user_runtime', 'agent_sessions', ['user_id', 'runtime_id'])
    op.create_index('idx_session_token', 'agent_sessions', ['session_token_hash'])
    op.create_index('idx_session_status_activity', 'agent_sessions', ['status', 'last_activity_at'])

    # ================================================================
    # 7. AgentSessionMessage 会话消息表
    # ================================================================
    op.create_table(
        'agent_session_messages',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(length=20), nullable=False, default='text'),
        sa.Column('tool_calls', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('referenced_file_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=False, default=0),
        sa.Column('run_id', sa.String(length=100), nullable=True),
        sa.Column('trace_id', sa.String(length=100), nullable=True),
        sa.Column('is_error', sa.Boolean(), nullable=False, default=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_message_session_created', 'agent_session_messages', ['session_id', 'created_at'])
    op.create_index('idx_message_role_created', 'agent_session_messages', ['role', 'created_at'])
    op.create_index('idx_message_run_id', 'agent_session_messages', ['run_id'])

    # ================================================================
    # 8. AgentSessionCheckpoint 会话检查点表
    # ================================================================
    op.create_table(
        'agent_session_checkpoints',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('checkpoint_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('checkpoint_type', sa.String(length=20), nullable=False, default='manual'),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_checkpoint_session_created', 'agent_session_checkpoints', ['session_id', 'created_at'])
    op.create_index('idx_checkpoint_type', 'agent_session_checkpoints', ['checkpoint_type'])


def downgrade() -> None:
    # 注意：downgrade 会删除表和相关数据
    # 生产环境请谨慎执行
    # 按相反顺序删除表（先删除依赖表，再删除被依赖表）
    op.drop_table('agent_session_checkpoints')
    op.drop_table('agent_session_messages')
    op.drop_table('agent_sessions')
    op.drop_table('agent_runtime_events')
    op.drop_table('workspace_files')
    op.drop_table('workspace_audit_logs')
    op.drop_table('agent_runtimes')
    op.drop_table('workspaces')
