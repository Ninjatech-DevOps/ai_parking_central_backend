from sqlalchemy import String, Boolean
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin, TimestampMixin


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fcm_tokens = mapped_column(ARRAY(String), nullable=True, default=[])

    user_roles = relationship("UserRole", back_populates="user", lazy="selectin")
    user_scopes = relationship("UserScope", back_populates="user", lazy="selectin")
    notification_preferences = relationship(
        "NotificationPreference", back_populates="user", lazy="selectin"
    )
