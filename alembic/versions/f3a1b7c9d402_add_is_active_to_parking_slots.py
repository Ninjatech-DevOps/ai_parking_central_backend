"""add is_active to parking_slots

Revision ID: f3a1b7c9d402
Revises: c807e2ed5c35
Create Date: 2026-05-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a1b7c9d402"
down_revision: Union[str, None] = "5774a60ff5d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "parking_slots",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_parking_slots_is_active", "parking_slots", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_parking_slots_is_active", table_name="parking_slots")
    op.drop_column("parking_slots", "is_active")
