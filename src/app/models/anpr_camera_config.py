from sqlalchemy import Boolean, ForeignKey, String, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import AnprDirection
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class AnprCameraConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "anpr_camera_configs"

    camera_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, unique=True
    )
    roi_coords: Mapped[str] = mapped_column(Text, nullable=True)  # JSON: [[x1,y1], ...]
    trigger_line: Mapped[str] = mapped_column(Text, nullable=True)  # JSON: [[x1,y1], [x2,y2]]
    direction: Mapped[str] = mapped_column(
        SAEnum(AnprDirection, name="anpr_direction_enum"),
        nullable=False,
        default=AnprDirection.IN,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    camera = relationship("Camera", back_populates="anpr_config", lazy="selectin")
