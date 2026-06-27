from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin


class ParkingScan(Base, UUIDMixin):
    """One row per detection scan. Simplified parking history."""

    __tablename__ = "parking_scans"

    device_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    camera_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False
    )
    location_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    city_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cities.id"), nullable=True
    )
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    car_occupied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    car_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    car_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    two_wheeler_occupied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    two_wheeler_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    two_wheeler_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_obstruction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    device = relationship("Device", lazy="selectin")
    camera = relationship("Camera", lazy="selectin")
    location = relationship("Location", lazy="selectin")
