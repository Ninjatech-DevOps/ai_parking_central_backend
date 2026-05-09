from sqlalchemy import String, Float, Integer, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import LocationType
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Location(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "locations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    area_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("areas.id"), nullable=False
    )
    address: Mapped[str] = mapped_column(String(500), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    location_type: Mapped[str] = mapped_column(
        SAEnum(LocationType, name="location_type_enum"),
        nullable=False,
        default=LocationType.OPEN,
    )
    total_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    area = relationship("Area", back_populates="locations", lazy="selectin")
    floors = relationship("Floor", back_populates="location", lazy="selectin")
    devices = relationship("Device", back_populates="location", lazy="selectin")
