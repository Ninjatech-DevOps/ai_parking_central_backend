from sqlalchemy import String, Float, Integer, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import CameraStatus, CameraType
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Camera(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cameras"

    device_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    position_label: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=True)  # "0", "rtsp://...", "csi://0"
    camera_type: Mapped[str] = mapped_column(
        SAEnum(CameraType, name="camera_type_central_enum"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        SAEnum(CameraStatus, name="camera_status_enum"),
        nullable=False,
        default=CameraStatus.ACTIVE,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    detection_interval: Mapped[float] = mapped_column(Float, nullable=True, default=30.0)

    # Frame dimensions (set from snapshot capture)
    frame_width: Mapped[int] = mapped_column(Integer, nullable=True)
    frame_height: Mapped[int] = mapped_column(Integer, nullable=True)

    # Reference snapshot path (for polygon drawing in Central FE)
    snapshot_path: Mapped[str] = mapped_column(String(500), nullable=True)

    device = relationship("Device", back_populates="cameras", lazy="selectin")
    slots = relationship("ParkingSlot", back_populates="camera", lazy="selectin")
