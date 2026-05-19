from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import NotificationChannel
from src.app.db.base import Base, UUIDMixin


class NotificationLog(Base, UUIDMixin):
    __tablename__ = "notification_logs"

    user_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    alert_event_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_events.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(
        SAEnum(NotificationChannel, name="notification_channel_enum", create_type=False),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    error: Mapped[str] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", lazy="selectin")
    alert_event = relationship("AlertEvent", lazy="selectin")
