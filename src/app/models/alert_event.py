from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import AlertSeverity, AlertStatus
from src.app.db.base import Base, UUIDMixin


class AlertEvent(Base, UUIDMixin):
    __tablename__ = "alert_events"

    alert_rule_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id"), nullable=False
    )
    device_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True
    )
    location_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True
    )
    severity: Mapped[str] = mapped_column(
        SAEnum(AlertSeverity, name="alert_severity_enum", create_type=False),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(AlertStatus, name="alert_status_enum"),
        nullable=False,
        default=AlertStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    alert_rule = relationship("AlertRule", lazy="selectin")
    device = relationship("Device", lazy="selectin")
    location = relationship("Location", lazy="selectin")
    acknowledger = relationship("User", lazy="selectin")
