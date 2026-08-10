"""add metadata_json to documents

Revision ID: 011
Revises: 010
Create Date: 2026-08-04 17:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '011'
down_revision: Union[str, Sequence[str], None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add metadata_json column to documents table."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('metadata_json', sa.String(length=2000), nullable=True))


def downgrade() -> None:
    """Remove metadata_json column from documents table."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_column('metadata_json')
