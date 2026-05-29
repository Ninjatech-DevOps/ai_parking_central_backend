"""add result column to device_commands

Revision ID: d3a2270259e1
Revises: f4a2b8c1d903
Create Date: 2026-05-28 15:51:42.357042

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3a2270259e1'
down_revision: Union[str, None] = 'f4a2b8c1d903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('device_commands', sa.Column('result', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('device_commands', 'result')
