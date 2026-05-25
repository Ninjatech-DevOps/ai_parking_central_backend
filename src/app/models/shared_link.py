import secrets
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import SharedLinkScopeType
from src.app.db.base import Base, UUIDMixin, TimestampMixin


def generate_token() -> str:
    return secrets.token_urlsafe(16)


class SharedLink(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "shared_links"

    token: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, default=generate_token, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=True)
    scope_type: Mapped[str] = mapped_column(
        SAEnum(SharedLinkScopeType, name="shared_link_scope_type_enum"),
        nullable=False,
    )
    scope_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    camera_ids: Mapped[str] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_by = relationship("User", lazy="selectin")
