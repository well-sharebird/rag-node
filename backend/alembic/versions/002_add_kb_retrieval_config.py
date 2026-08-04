"""add kb retrieval config

Revision ID: 002
Revises: 001
Create Date: 2026-07-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create knowledge_bases table if not exists (moved from later migration)
    op.create_table('knowledge_bases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner', sa.String(length=255), nullable=True),
        sa.Column('top_k', sa.Integer(), nullable=True),
        sa.Column('min_score', sa.Float(), nullable=True),
        sa.Column('enable_rerank', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_kb_name', 'knowledge_bases', ['name'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_kb_name', table_name='knowledge_bases')
    op.drop_table('knowledge_bases')
