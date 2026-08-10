"""add execution traces table

Revision ID: 013
Revises: 012
Create Date: 2026-08-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create execution_traces table
    op.create_table('execution_traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_id', sa.String(length=100), nullable=False),
        sa.Column('thread_id', sa.String(length=200), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_name', sa.String(length=200), nullable=True),
        sa.Column('agent_type', sa.String(length=50), nullable=True),
        sa.Column('intent_type', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('tool_calls', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('input_summary', sa.Text(), nullable=True),
        sa.Column('output_summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_execution_traces_run_id', 'execution_traces', ['run_id'], unique=True)
    op.create_index('ix_execution_traces_thread_id', 'execution_traces', ['thread_id'])
    op.create_index('ix_execution_traces_user_id', 'execution_traces', ['user_id'])
    op.create_index('ix_execution_traces_tenant_id', 'execution_traces', ['tenant_id'])
    op.create_index('ix_execution_traces_agent_id', 'execution_traces', ['agent_id'])
    op.create_index('ix_execution_traces_status', 'execution_traces', ['status'])
    op.create_index('ix_execution_traces_created_at', 'execution_traces', ['created_at'])
    op.create_index('ix_execution_traces_user_created', 'execution_traces', ['user_id', 'created_at'])
    op.create_index('ix_execution_traces_agent_created', 'execution_traces', ['agent_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_execution_traces_agent_created')
    op.drop_index('ix_execution_traces_user_created')
    op.drop_index('ix_execution_traces_created_at')
    op.drop_index('ix_execution_traces_status')
    op.drop_index('ix_execution_traces_agent_id')
    op.drop_index('ix_execution_traces_tenant_id')
    op.drop_index('ix_execution_traces_user_id')
    op.drop_index('ix_execution_traces_thread_id')
    op.drop_index('ix_execution_traces_run_id')
    op.drop_table('execution_traces')
