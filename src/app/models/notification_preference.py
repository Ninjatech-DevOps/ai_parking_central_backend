from sqlalchemy import Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import AlertSeverity, NotificationChannel
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class NotificationPreference(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "notification_preferences"

    user_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    alert_severity: Mapped[str] = mapped_column(
        SAEnum(AlertSeverity, name="alert_severity_enum", create_type=False),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(
        SAEnum(NotificationChannel, name="notification_channel_enum"),
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="notification_preferences", lazy="selectin")
