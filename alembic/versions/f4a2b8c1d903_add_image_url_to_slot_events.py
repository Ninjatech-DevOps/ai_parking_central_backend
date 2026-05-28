"""add image_url to slot_events

Revision ID: f4a2b8c1d903
Revises: e069085eb092
Create Date: 2026-05-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a2b8c1d903'
down_revision: Union[str, None] = 'e069085eb092'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('slot_events', sa.Column('image_url', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('slot_events', 'image_url')
