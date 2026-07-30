"""add agent tables

Revision ID: 005
Revises: 004
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create agent_configs table
    op.create_table(
        'agent_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(length=500), nullable=True),
        sa.Column('agent_type', sa.String(length=20), nullable=False, server_default='single'),
        sa.Column('default_model_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('enabled_skills', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('mcp_servers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('memory_type', sa.String(length=20), nullable=False, server_default='conversation'),
        sa.Column('memory_ttl_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('max_memory_turns', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('kb_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('retrieval_top_k', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('retrieval_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('multi_agent_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('current_version', sa.String(length=20), nullable=False, server_default='1.0.0'),
        sa.Column('total_runs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_agent_configs_user_id', 'agent_configs', ['user_id'], unique=False)
    op.create_index('idx_agent_user_status', 'agent_configs', ['user_id', 'status'], unique=False)
    op.create_index('idx_agent_tenant', 'agent_configs', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_agent_configs_name', 'agent_configs', ['name'], unique=False)

    # Create agent_versions table
    op.create_table(
        'agent_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('config_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('changelog', sa.Text(), nullable=True),
        sa.Column('published_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_id', 'version', name='uq_agent_version')
    )
    op.create_index('ix_agent_versions_agent_id', 'agent_versions', ['agent_id'], unique=False)
    op.create_index('idx_version_agent_created', 'agent_versions', ['agent_id', 'created_at'], unique=False)

    # Create agent_memories table
    op.create_table(
        'agent_memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('thread_id', sa.String(length=200), nullable=False),
        sa.Column('memory_type', sa.String(length=20), nullable=False),
        sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('milvus_collection', sa.String(length=200), nullable=True),
        sa.Column('milvus_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_agent_memories_agent_id', 'agent_memories', ['agent_id'], unique=False)
    op.create_index('ix_agent_memories_user_id', 'agent_memories', ['user_id'], unique=False)
    op.create_index('ix_agent_memories_thread_id', 'agent_memories', ['thread_id'], unique=False)
    op.create_index('idx_memory_user_agent_thread', 'agent_memories', ['user_id', 'agent_id', 'thread_id'], unique=False)
    op.create_index('idx_memory_expires', 'agent_memories', ['expires_at'], unique=False)

    # Create agent_call_logs table
    op.create_table(
        'agent_call_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('thread_id', sa.String(length=200), nullable=True),
        sa.Column('run_id', sa.String(length=100), nullable=False),
        sa.Column('model_provider', sa.String(length=100), nullable=True),
        sa.Column('model_name', sa.String(length=200), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_token_latency_ms', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('input_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_agent_call_logs_agent_id', 'agent_call_logs', ['agent_id'], unique=False)
    op.create_index('ix_agent_call_logs_user_id', 'agent_call_logs', ['user_id'], unique=False)
    op.create_index('ix_agent_call_logs_run_id', 'agent_call_logs', ['run_id'], unique=False)
    op.create_index('ix_agent_call_logs_thread_id', 'agent_call_logs', ['thread_id'], unique=False)
    op.create_index('idx_agent_call_agent_created', 'agent_call_logs', ['agent_id', 'created_at'], unique=False)
    op.create_index('idx_agent_call_user_created', 'agent_call_logs', ['user_id', 'created_at'], unique=False)

    # Add foreign key constraints
    op.create_foreign_key(
        'fk_agent_configs_user_id',
        'agent_configs', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_agent_versions_agent_id',
        'agent_versions', 'agent_configs',
        ['agent_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_agent_memories_agent_id',
        'agent_memories', 'agent_configs',
        ['agent_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_agent_memories_user_id',
        'agent_memories', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_agent_call_logs_agent_id',
        'agent_call_logs', 'agent_configs',
        ['agent_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_agent_call_logs_user_id',
        'agent_call_logs', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Drop tables in reverse order (due to foreign keys)
    op.drop_table('agent_call_logs')
    op.drop_table('agent_memories')
    op.drop_table('agent_versions')
    op.drop_table('agent_configs')
