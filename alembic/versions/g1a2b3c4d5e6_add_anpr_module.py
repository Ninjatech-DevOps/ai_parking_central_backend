"""Add ANPR module: camera module_type, location slot totals, ANPR tables

Revision ID: g1a2b3c4d5e6
Revises: a81161e2e1b0
Create Date: 2026-06-27 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "g1a2b3c4d5e6"
down_revision: str = "a81161e2e1b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums (safe: skip if already exists — SQLAlchemy may auto-create them on app start)
    op.execute("DO $$ BEGIN CREATE TYPE camera_module_type_enum AS ENUM ('AI_PARKING', 'ANPR'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE anpr_direction_enum AS ENUM ('IN', 'OUT'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE vehicle_type_enum AS ENUM ('CAR', 'TWO_WHEELER'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

    # Add module_type to cameras (safe: skip if column already exists from partial run)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cameras ADD COLUMN module_type camera_module_type_enum NOT NULL DEFAULT 'AI_PARKING';
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$;
    """)

    # Add slot totals to locations
    op.execute("DO $$ BEGIN ALTER TABLE locations ADD COLUMN total_car_slots INTEGER NOT NULL DEFAULT 0; EXCEPTION WHEN duplicate_column THEN NULL; END $$;")
    op.execute("DO $$ BEGIN ALTER TABLE locations ADD COLUMN total_two_wheeler_slots INTEGER NOT NULL DEFAULT 0; EXCEPTION WHEN duplicate_column THEN NULL; END $$;")

    # Create tables using raw SQL to avoid SQLAlchemy enum auto-creation issues
    op.execute("""
        CREATE TABLE IF NOT EXISTS anpr_camera_configs (
            id UUID PRIMARY KEY,
            camera_id UUID NOT NULL UNIQUE REFERENCES cameras(id),
            roi_coords TEXT,
            trigger_line TEXT,
            direction anpr_direction_enum NOT NULL DEFAULT 'IN',
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS anpr_records (
            id UUID PRIMARY KEY,
            device_id UUID NOT NULL REFERENCES devices(id),
            camera_id UUID NOT NULL REFERENCES cameras(id),
            location_id UUID NOT NULL REFERENCES locations(id),
            city_id UUID REFERENCES cities(id),
            number_plate VARCHAR(30) NOT NULL,
            vehicle_type vehicle_type_enum NOT NULL DEFAULT 'CAR',
            direction anpr_direction_enum NOT NULL,
            image_url VARCHAR(500),
            gemini_result VARCHAR(30),
            paddle_result VARCHAR(30),
            confidence_gemini FLOAT,
            confidence_paddle FLOAT,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_anpr_records_recorded_at ON anpr_records (recorded_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_anpr_records_number_plate ON anpr_records (number_plate);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_anpr_records_location_id ON anpr_records (location_id);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS anpr_sessions (
            id UUID PRIMARY KEY,
            location_id UUID NOT NULL REFERENCES locations(id),
            city_id UUID REFERENCES cities(id),
            number_plate VARCHAR(30) NOT NULL,
            vehicle_type vehicle_type_enum NOT NULL DEFAULT 'CAR',
            entry_record_id UUID NOT NULL REFERENCES anpr_records(id),
            exit_record_id UUID REFERENCES anpr_records(id),
            entry_time TIMESTAMPTZ NOT NULL,
            exit_time TIMESTAMPTZ,
            entry_image_url VARCHAR(500),
            exit_image_url VARCHAR(500),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_anpr_sessions_number_plate ON anpr_sessions (number_plate);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_anpr_sessions_location_id ON anpr_sessions (location_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_anpr_sessions_entry_time ON anpr_sessions (entry_time);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_anpr_sessions_is_active ON anpr_sessions (is_active);")

    # Note: TimescaleDB hypertable conversion skipped for anpr_records.
    # Can be added later when data volume justifies it (requires composite PK with recorded_at).


def downgrade() -> None:
    op.drop_table("anpr_sessions")
    op.drop_table("anpr_records")
    op.drop_table("anpr_camera_configs")
    op.drop_column("locations", "total_two_wheeler_slots")
    op.drop_column("locations", "total_car_slots")
    op.drop_column("cameras", "module_type")
    sa.Enum(name="anpr_direction_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="camera_module_type_enum").drop(op.get_bind(), checkfirst=True)
