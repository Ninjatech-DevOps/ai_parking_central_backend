from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin, TimestampMixin


class City(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cities"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    state_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("states.id"), nullable=False
    )

    state = relationship("State", back_populates="cities", lazy="selectin")
    talukas = relationship("Taluka", back_populates="city", lazy="selectin")
    areas = relationship("Area", back_populates="city", lazy="selectin")
