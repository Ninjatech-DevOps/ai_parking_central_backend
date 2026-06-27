from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import AnprDirection, VehicleType
from src.app.db.base import Base, UUIDMixin


class AnprRecord(Base, UUIDMixin):
    """Time-series table for individual ANPR detections. Will be a TimescaleDB hypertable."""

    __tablename__ = "anpr_records"

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
    number_plate: Mapped[str] = mapped_column(String(30), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(
        SAEnum(VehicleType, name="vehicle_type_enum", create_type=False),
        nullable=False,
        default=VehicleType.CAR,
    )
    direction: Mapped[str] = mapped_column(
        SAEnum(AnprDirection, name="anpr_direction_enum", create_type=False),
        nullable=False,
    )
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    gemini_result: Mapped[str] = mapped_column(String(30), nullable=True)
    paddle_result: Mapped[str] = mapped_column(String(30), nullable=True)
    confidence_gemini: Mapped[float] = mapped_column(Float, nullable=True)
    confidence_paddle: Mapped[float] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    device = relationship("Device", lazy="selectin")
    camera = relationship("Camera", lazy="selectin")
    location = relationship("Location", lazy="selectin")
