from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Taluka(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "talukas"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    city_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cities.id"), nullable=False
    )

    city = relationship("City", back_populates="talukas", lazy="selectin")
    villages = relationship("Village", back_populates="taluka", lazy="selectin")
