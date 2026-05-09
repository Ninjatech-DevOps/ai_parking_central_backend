from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base, UUIDMixin, TimestampMixin


class Permission(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "permissions"

    resource: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)

    role_permissions = relationship(
        "RolePermission", back_populates="permission", lazy="selectin"
    )

    @property
    def key(self) -> str:
        return f"{self.resource}:{self.action}"
