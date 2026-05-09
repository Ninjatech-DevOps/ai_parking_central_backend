from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Area(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "areas"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    city_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cities.id"), nullable=False
    )
    taluka_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("talukas.id"), nullable=True
    )
    village_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("villages.id"), nullable=True
    )

    city = relationship("City", back_populates="areas", lazy="selectin")
    taluka = relationship("Taluka", lazy="selectin")
    village = relationship("Village", back_populates="areas", lazy="selectin")
    locations = relationship("Location", back_populates="area", lazy="selectin")
