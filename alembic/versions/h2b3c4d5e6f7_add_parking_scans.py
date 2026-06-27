"""Add parking_scans table for simplified parking history

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-06-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h2b3c4d5e6f7"
down_revision: str = "g1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS parking_scans (
            id UUID PRIMARY KEY,
            device_id UUID NOT NULL REFERENCES devices(id),
            camera_id UUID NOT NULL REFERENCES cameras(id),
            location_id UUID NOT NULL REFERENCES locations(id),
            city_id UUID REFERENCES cities(id),
            image_url VARCHAR(500),
            car_occupied INTEGER NOT NULL DEFAULT 0,
            car_available INTEGER NOT NULL DEFAULT 0,
            car_total INTEGER NOT NULL DEFAULT 0,
            two_wheeler_occupied INTEGER NOT NULL DEFAULT 0,
            two_wheeler_available INTEGER NOT NULL DEFAULT 0,
            two_wheeler_total INTEGER NOT NULL DEFAULT 0,
            has_obstruction BOOLEAN NOT NULL DEFAULT false,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_parking_scans_recorded_at ON parking_scans (recorded_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_parking_scans_location_id ON parking_scans (location_id);")


def downgrade() -> None:
    op.drop_table("parking_scans")
