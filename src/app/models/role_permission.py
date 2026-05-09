from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin


class RolePermission(Base, UUIDMixin):
    __tablename__ = "role_permissions"

    role_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    permission_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id"), nullable=False
    )

    role = relationship("Role", back_populates="role_permissions", lazy="selectin")
    permission = relationship(
        "Permission", back_populates="role_permissions", lazy="selectin"
    )
