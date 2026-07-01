"""add view_config to shared_links

Revision ID: i3c4d5e6f7g8
Revises: h2b3c4d5e6f7
Create Date: 2026-07-01 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i3c4d5e6f7g8'
down_revision: Union[str, None] = 'h2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('shared_links', sa.Column('view_config', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('shared_links', 'view_config')
