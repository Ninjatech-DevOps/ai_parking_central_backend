"""add vehicle_movements table

Revision ID: k5e6f7g8h9i0
Revises: j4d5e6f7g8h9
Create Date: 2026-08-21 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'k5e6f7g8h9i0'
down_revision: Union[str, None] = 'j4d5e6f7g8h9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Its own enum type rather than reusing anpr_direction_enum: movements are
    # counted independently of plate recognition and should not be coupled to
    # the ANPR module's schema.
    postgresql.ENUM(
        'IN', 'OUT', name='vehicle_movement_direction_enum'
    ).create(op.get_bind(), checkfirst=True)

    # create_type=False because the line above already created it — without
    # this, create_table emits a second CREATE TYPE and the migration fails
    # with DuplicateObjectError.
    direction_enum = postgresql.ENUM(
        'IN', 'OUT', name='vehicle_movement_direction_enum', create_type=False
    )

    op.create_table(
        'vehicle_movements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('location_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('camera_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=True),
        # vehicle_type_enum already exists (anpr_records uses it), so bind to it
        # without trying to create it a second time.
        sa.Column(
            'vehicle_type',
            postgresql.ENUM(
                'CAR', 'TWO_WHEELER', name='vehicle_type_enum', create_type=False
            ),
            nullable=False,
            server_default='CAR',
        ),
        sa.Column('direction', direction_enum, nullable=False),
        sa.Column('number_plate', sa.String(length=30), nullable=True),
        sa.Column(
            'recorded_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id']),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id']),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index(
        'ix_vehicle_movements_location_id', 'vehicle_movements', ['location_id']
    )
    op.create_index(
        'ix_vehicle_movements_camera_id', 'vehicle_movements', ['camera_id']
    )
    op.create_index(
        'ix_vehicle_movements_recorded_at', 'vehicle_movements', ['recorded_at']
    )
    # Composite indexes matching the list API's ORDER BY, so paging stays on an
    # index scan instead of degrading to a sequential scan plus sort as the
    # table grows.
    op.create_index(
        'ix_vehicle_movements_location_recorded',
        'vehicle_movements',
        ['location_id', sa.text('recorded_at DESC')],
    )
    op.create_index(
        'ix_vehicle_movements_camera_recorded',
        'vehicle_movements',
        ['camera_id', sa.text('recorded_at DESC')],
    )


def downgrade() -> None:
    op.drop_index('ix_vehicle_movements_camera_recorded', table_name='vehicle_movements')
    op.drop_index('ix_vehicle_movements_location_recorded', table_name='vehicle_movements')
    op.drop_index('ix_vehicle_movements_recorded_at', table_name='vehicle_movements')
    op.drop_index('ix_vehicle_movements_camera_id', table_name='vehicle_movements')
    op.drop_index('ix_vehicle_movements_location_id', table_name='vehicle_movements')
    op.drop_table('vehicle_movements')
    postgresql.ENUM(name='vehicle_movement_direction_enum').drop(
        op.get_bind(), checkfirst=True
    )
