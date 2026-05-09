from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Village(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "villages"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    taluka_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("talukas.id"), nullable=False
    )

    taluka = relationship("Taluka", back_populates="villages", lazy="selectin")
    areas = relationship("Area", back_populates="village", lazy="selectin")
