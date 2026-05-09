from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin, TimestampMixin


class State(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "states"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="India")

    cities = relationship("City", back_populates="state", lazy="selectin")
