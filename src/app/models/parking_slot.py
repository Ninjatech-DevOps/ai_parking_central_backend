from sqlalchemy import String, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import SlotState
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class ParkingSlot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "parking_slots"

    label: Mapped[str] = mapped_column(String(20), nullable=False)
    zone_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(
        SAEnum(SlotState, name="slot_state_enum"),
        nullable=False,
        default=SlotState.EMPTY,
    )

    zone = relationship("Zone", back_populates="parking_slots", lazy="selectin")
    slot_events = relationship("SlotEvent", back_populates="parking_slot", lazy="noload")
