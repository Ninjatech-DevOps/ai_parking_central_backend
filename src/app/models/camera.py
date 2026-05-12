from sqlalchemy import String, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import CameraStatus
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Camera(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cameras"

    device_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    position_label: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(CameraStatus, name="camera_status_enum"),
        nullable=False,
        default=CameraStatus.ACTIVE,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    device = relationship("Device", back_populates="cameras", lazy="selectin")
    slots = relationship("ParkingSlot", back_populates="camera", lazy="selectin")
