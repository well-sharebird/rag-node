"""add conversation archives

Revision ID: 008
Revises: d25f0a5721d3
Create Date: 2026-07-30

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008'
down_revision = 'd25f0a5721d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create conversation_archives table
    op.create_table(
        'conversation_archives',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('thread_id', sa.String(length=200), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_name', sa.String(length=200), nullable=True),
        sa.Column('archive_tier', sa.String(length=20), nullable=False),
        sa.Column('message_count', sa.Integer(), nullable=False, default=0),
        sa.Column('compressed_content', sa.LargeBinary(), nullable=True),
        sa.Column('archive_path', sa.String(length=500), nullable=True),
        sa.Column('archive_size_bytes', sa.BigInteger(), nullable=False, default=0),
        sa.Column('date_range_start', sa.DateTime(), nullable=False),
        sa.Column('date_range_end', sa.DateTime(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('keywords', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_message_preview', sa.Text(), nullable=True),
        sa.Column('last_message_at', sa.DateTime(), nullable=False),
        sa.Column('is_restored', sa.Boolean(), nullable=False, default=False),
        sa.Column('archived_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for conversation_archives
    op.create_index('idx_archive_user_id', 'conversation_archives', ['user_id'])
    op.create_index('idx_archive_thread_id', 'conversation_archives', ['thread_id'])
    op.create_index('idx_archive_agent_id', 'conversation_archives', ['agent_id'])
    op.create_index('idx_archive_tier', 'conversation_archives', ['archive_tier'])
    op.create_index('idx_archive_date_range', 'conversation_archives', ['date_range_start', 'date_range_end'])
    op.create_index('idx_archive_last_message', 'conversation_archives', ['last_message_at'])
    op.create_index('idx_archive_archived_at', 'conversation_archives', ['archived_at'])

    # Create foreign keys
    op.create_foreign_key(
        'fk_conversation_archives_user_id',
        'conversation_archives', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_conversation_archives_agent_id',
        'conversation_archives', 'agent_configs',
        ['agent_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create conversation_archive_configs table
    op.create_table(
        'conversation_archive_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_name', sa.String(length=100), nullable=False),
        sa.Column('hot_tier_days', sa.Integer(), nullable=False, default=7),
        sa.Column('warm_tier_days', sa.Integer(), nullable=False, default=30),
        sa.Column('cold_tier_days', sa.Integer(), nullable=False, default=365),
        sa.Column('archive_batch_size', sa.Integer(), nullable=False, default=100),
        sa.Column('min_message_count', sa.Integer(), nullable=False, default=5),
        sa.Column('compression_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('compression_level', sa.Integer(), nullable=False, default=6),
        sa.Column('minio_bucket', sa.String(length=100), nullable=False, default='conversation-archives'),
        sa.Column('minio_prefix', sa.String(length=200), nullable=False, default='archives'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.utcnow()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_name')
    )

    # Insert default config
    op.execute("""
        INSERT INTO conversation_archive_configs (
            config_name, hot_tier_days, warm_tier_days, cold_tier_days,
            archive_batch_size, min_message_count, compression_enabled,
            compression_level, minio_bucket, minio_prefix, is_enabled
        ) VALUES (
            'default', 7, 30, 365, 100, 5, true, 6,
            'conversation-archives', 'archives', true
        )
    """)


def downgrade() -> None:
    op.drop_table('conversation_archive_configs')
    op.drop_table('conversation_archives')
