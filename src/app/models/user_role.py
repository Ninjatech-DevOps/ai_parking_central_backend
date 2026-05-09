from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin


class UserRole(Base, UUIDMixin):
    __tablename__ = "user_roles"

    user_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    role_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )

    user = relationship("User", back_populates="user_roles", lazy="selectin")
    role = relationship("Role", back_populates="user_roles", lazy="selectin")
