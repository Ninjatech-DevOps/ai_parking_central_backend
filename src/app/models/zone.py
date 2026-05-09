from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Zone(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "zones"

    name: Mapped[str] = mapped_column(String(50), nullable=False)
    floor_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("floors.id"), nullable=False
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    floor = relationship("Floor", back_populates="zones", lazy="selectin")
    parking_slots = relationship("ParkingSlot", back_populates="zone", lazy="selectin")
