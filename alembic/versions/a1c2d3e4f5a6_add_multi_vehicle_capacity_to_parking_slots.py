"""add multi-vehicle capacity to parking_slots

Revision ID: a1c2d3e4f5a6
Revises: d3a2270259e1
Create Date: 2026-06-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c2d3e4f5a6'
down_revision: Union[str, None] = 'd3a2270259e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('parking_slots', sa.Column('capacity_car', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('parking_slots', sa.Column('capacity_two_wheeler', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('parking_slots', sa.Column('occupied_car', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('parking_slots', sa.Column('occupied_two_wheeler', sa.Integer(), nullable=False, server_default='0'))

    # Backfill existing single-vehicle slots: set capacity based on slot_type
    op.execute("""
        UPDATE parking_slots SET capacity_car = 1 WHERE slot_type = 'CAR';
    """)
    op.execute("""
        UPDATE parking_slots SET capacity_two_wheeler = 1 WHERE slot_type = 'TWO_WHEELER';
    """)
    op.execute("""
        UPDATE parking_slots SET capacity_car = 1 WHERE slot_type = 'GENERAL';
    """)


def downgrade() -> None:
    op.drop_column('parking_slots', 'occupied_two_wheeler')
    op.drop_column('parking_slots', 'occupied_car')
    op.drop_column('parking_slots', 'capacity_two_wheeler')
    op.drop_column('parking_slots', 'capacity_car')
