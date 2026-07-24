"""add model gateway tables

Revision ID: 003
Revises: 002
Create Date: 2025-07-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create model_providers table
    op.create_table('model_providers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('provider_type', sa.String(50), nullable=False),
        sa.Column('region', sa.String(100), nullable=True),
        sa.Column('base_url', sa.String(500), nullable=False),
        sa.Column('api_version', sa.String(50), nullable=True),
        sa.Column('auth_type', sa.String(50), nullable=False, server_default='api_key'),
        sa.Column('api_key_name', sa.String(100), nullable=True),
        sa.Column('api_key', sa.String(1000), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='t'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='f'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('health_status', sa.String(20), nullable=True),
        sa.Column('last_health_check', sa.DateTime(), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rate_limit_enabled', sa.Boolean(), nullable=False, server_default='f'),
        sa.Column('rate_limit_requests', sa.Integer(), nullable=True),
        sa.Column('rate_limit_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_input', sa.Numeric(10, 6), nullable=True),
        sa.Column('cost_output', sa.Numeric(10, 6), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_model_providers_code', 'model_providers', ['code'], unique=False)

    # Create model_routing_rules table
    op.create_table('model_routing_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('model_type', sa.String(50), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('match_conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('traffic_weight', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('failover_enabled', sa.Boolean(), nullable=False, server_default='f'),
        sa.Column('failover_provider_id', sa.Integer(), nullable=True),
        sa.Column('failover_threshold', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('failover_window_seconds', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('timeout_ms', sa.Integer(), nullable=False, server_default='30000'),
        sa.Column('retry_enabled', sa.Boolean(), nullable=False, server_default='f'),
        sa.Column('retry_max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('retry_delay_ms', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='t'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['provider_id'], ['model_providers.id'], ),
        sa.ForeignKeyConstraint(['failover_provider_id'], ['model_providers.id'], )
    )
    op.create_index('idx_routing_type_priority', 'model_routing_rules', ['model_type', 'priority'], unique=False)

    # Create model_call_logs table
    op.create_table('model_call_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_id', sa.String(100), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('model_id', sa.String(200), nullable=False),
        sa.Column('model_type', sa.String(50), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('app_id', sa.String(100), nullable=True),
        sa.Column('kb_id', sa.String(36), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_token_latency_ms', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('cost', sa.Numeric(12, 8), nullable=True),
        sa.Column('cached', sa.Boolean(), nullable=False, server_default='f'),
        sa.Column('request_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_id'),
        sa.ForeignKeyConstraint(['provider_id'], ['model_providers.id'], )
    )
    op.create_index('ix_model_call_logs_request_id', 'model_call_logs', ['request_id'], unique=False)
    op.create_index('ix_model_call_logs_provider_id', 'model_call_logs', ['provider_id'], unique=False)
    op.create_index('ix_model_call_logs_model_type', 'model_call_logs', ['model_type'], unique=False)
    op.create_index('ix_model_call_logs_user_id', 'model_call_logs', ['user_id'], unique=False)
    op.create_index('ix_model_call_logs_app_id', 'model_call_logs', ['app_id'], unique=False)
    op.create_index('ix_model_call_logs_kb_id', 'model_call_logs', ['kb_id'], unique=False)
    op.create_index('ix_model_call_logs_created_at', 'model_call_logs', ['created_at'], unique=False)
    op.create_index('idx_call_provider_created', 'model_call_logs', ['provider_id', 'created_at'], unique=False)
    op.create_index('idx_call_user_created', 'model_call_logs', ['user_id', 'created_at'], unique=False)

    # Create model_caches table
    op.create_table('model_caches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cache_key', sa.String(500), nullable=False),
        sa.Column('model_type', sa.String(50), nullable=False),
        sa.Column('model_id', sa.String(200), nullable=False),
        sa.Column('response_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ttl_seconds', sa.Integer(), nullable=False, server_default='3600'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('hit_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_hit_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cache_key')
    )
    op.create_index('ix_model_caches_cache_key', 'model_caches', ['cache_key'], unique=False)
    op.create_index('idx_cache_expires', 'model_caches', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_table('model_caches')
    op.drop_table('model_call_logs')
    op.drop_table('model_routing_rules')
    op.drop_table('model_providers')
