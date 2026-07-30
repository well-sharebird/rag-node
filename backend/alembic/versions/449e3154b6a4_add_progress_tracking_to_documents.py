"""add progress tracking to documents

Revision ID: 449e3154b6a4
Revises: 007
Create Date: 2026-07-29 15:26:20.662973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '449e3154b6a4'
down_revision: Union[str, Sequence[str], None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add progress tracking columns to documents table."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('progress', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('current_stage', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Remove progress tracking columns from documents table."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_column('current_stage')
        batch_op.drop_column('progress')
