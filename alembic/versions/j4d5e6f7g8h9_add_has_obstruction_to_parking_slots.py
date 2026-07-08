"""add has_obstruction to parking_slots

Revision ID: j4d5e6f7g8h9
Revises: i3c4d5e6f7g8
Create Date: 2026-07-08 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j4d5e6f7g8h9'
down_revision: Union[str, None] = 'i3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('parking_slots', sa.Column('has_obstruction', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('parking_slots', 'has_obstruction')
