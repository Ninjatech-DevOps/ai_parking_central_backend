from sqlalchemy import ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import ScopeType
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class UserScope(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_scopes"

    user_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(
        SAEnum(ScopeType, name="scope_type_enum"),
        nullable=False,
    )
    scope_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    user = relationship("User", back_populates="user_scopes", lazy="selectin")
