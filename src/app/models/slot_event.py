from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import SlotState
from src.app.db.base import Base, UUIDMixin


class SlotEvent(Base, UUIDMixin):
    """Time-series table for slot state changes. Will be a TimescaleDB hypertable."""

    __tablename__ = "slot_events"

    parking_slot_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parking_slots.id"), nullable=False
    )
    previous_state: Mapped[str] = mapped_column(
        SAEnum(SlotState, name="slot_state_enum", create_type=False),
        nullable=True,
    )
    new_state: Mapped[str] = mapped_column(
        SAEnum(SlotState, name="slot_state_enum", create_type=False),
        nullable=False,
    )
    device_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True
    )
    detected_vehicle_type: Mapped[str] = mapped_column(String(20), nullable=True)
    is_mismatched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    parking_slot = relationship("ParkingSlot", back_populates="slot_events", lazy="selectin")
    device = relationship("Device", lazy="selectin")
