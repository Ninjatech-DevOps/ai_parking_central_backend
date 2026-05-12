from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import DeviceStatus
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Device(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    location_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    zone_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True
    )
    # Denormalized for direct filtering
    city_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cities.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        SAEnum(DeviceStatus, name="device_status_enum"),
        nullable=False,
        default=DeviceStatus.OFFLINE,
    )
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)
    docker_image_version: Mapped[str] = mapped_column(String(50), nullable=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    location = relationship("Location", back_populates="devices", lazy="selectin")
    zone = relationship("Zone", lazy="selectin")
    cameras = relationship("Camera", back_populates="device", lazy="selectin")
