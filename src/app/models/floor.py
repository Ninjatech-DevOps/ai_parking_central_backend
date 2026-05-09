from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Floor(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "floors"

    location_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    level_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    location = relationship("Location", back_populates="floors", lazy="selectin")
    zones = relationship("Zone", back_populates="floor", lazy="selectin")
