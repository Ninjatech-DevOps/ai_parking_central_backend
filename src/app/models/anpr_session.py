from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import VehicleType
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class AnprSession(Base, UUIDMixin, TimestampMixin):
    """Tracks vehicle parking sessions: entry plate read → exit plate read."""

    __tablename__ = "anpr_sessions"

    location_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    city_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cities.id"), nullable=True
    )
    number_plate: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    vehicle_type: Mapped[str] = mapped_column(
        SAEnum(VehicleType, name="vehicle_type_enum", create_type=False),
        nullable=False,
        default=VehicleType.CAR,
    )
    entry_record_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anpr_records.id"), nullable=False
    )
    exit_record_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anpr_records.id"), nullable=True
    )
    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    exit_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    entry_image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    exit_image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    location = relationship("Location", lazy="selectin")
    entry_record = relationship("AnprRecord", foreign_keys=[entry_record_id], lazy="selectin")
    exit_record = relationship("AnprRecord", foreign_keys=[exit_record_id], lazy="selectin")
