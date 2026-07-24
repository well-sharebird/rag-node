"""add kb retrieval config

Revision ID: 002
Revises: 001
Create Date: 2026-07-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add retrieval config columns to knowledge_bases table
    op.add_column('knowledge_bases', sa.Column('top_k', sa.Integer(), nullable=True))
    op.add_column('knowledge_bases', sa.Column('min_score', sa.Float(), nullable=True))
    op.add_column('knowledge_bases', sa.Column('enable_rerank', sa.Boolean(), nullable=True))


def downgrade() -> None:
    # Remove retrieval config columns
    op.drop_column('knowledge_bases', 'enable_rerank')
    op.drop_column('knowledge_bases', 'min_score')
    op.drop_column('knowledge_bases', 'top_k')
