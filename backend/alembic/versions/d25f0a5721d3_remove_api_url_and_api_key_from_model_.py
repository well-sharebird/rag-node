"""remove api_url and api_key from model_configs

Revision ID: d25f0a5721d3
Revises: 449e3154b6a4
Create Date: 2026-07-30 16:00:29.035176

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd25f0a5721d3'
down_revision: Union[str, Sequence[str], None] = '449e3154b6a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove api_url and api_key columns from model_configs."""
    op.drop_column('model_configs', 'api_url')
    op.drop_column('model_configs', 'api_key')


def downgrade() -> None:
    """Restore api_url and api_key columns to model_configs."""
    op.add_column('model_configs', sa.Column('api_key', sa.String(length=500), nullable=True))
    op.add_column('model_configs', sa.Column('api_url', sa.String(length=500), nullable=True))
