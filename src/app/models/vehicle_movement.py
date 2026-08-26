from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Enum as SAEnum, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import MovementDirection, VehicleType
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class VehicleMovement(Base, UUIDMixin, TimestampMixin):
    """One row per vehicle entering or leaving a location.

    Event grain, not a running tally: ``direction`` is the source of truth and
    the In/Out columns the frontend renders are derived from it per row. Totals
    for a window are a COUNT over this table, so a period's figures can always
    be drilled back down to the movements that produced them.

    Deliberately independent of ``anpr_records`` — that table only exists where
    plate recognition runs and each row is tied to a detection. A movement here
    needs neither.
    """

    __tablename__ = "vehicle_movements"

    location_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False, index=True
    )
    # Nullable: a site may count at the gate rather than per camera.
    camera_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True, index=True
    )
    device_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True
    )
    vehicle_type: Mapped[str] = mapped_column(
        SAEnum(VehicleType, name="vehicle_type_enum", create_type=False),
        nullable=False,
        default=VehicleType.CAR,
    )
    direction: Mapped[str] = mapped_column(
        SAEnum(MovementDirection, name="vehicle_movement_direction_enum"),
        nullable=False,
    )
    # Optional — recorded when the counting source happens to know it.
    number_plate: Mapped[str] = mapped_column(String(30), nullable=True)

    # When the vehicle actually moved, which is not when the row was written.
    # Every filter and every ordering in the list API uses this column.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # noload, not the selectin used elsewhere in this codebase: loading a Camera
    # pulls all of that camera's slots (Camera.slots is selectin), which would
    # turn a 100-row page into thousands of rows of collateral. The list query
    # selects the two label columns it needs by explicit join instead.
    location = relationship("Location", lazy="noload")
    camera = relationship("Camera", lazy="noload")

    # The list API always narrows by location or camera and orders by time, so
    # these composites are what keep it off a sequential scan as the table
    # grows. DESC matches the ORDER BY exactly.
    __table_args__ = (
        Index(
            "ix_vehicle_movements_location_recorded",
            "location_id",
            text("recorded_at DESC"),
        ),
        Index(
            "ix_vehicle_movements_camera_recorded",
            "camera_id",
            text("recorded_at DESC"),
        ),
    )
