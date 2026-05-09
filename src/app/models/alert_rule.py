from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.app.core.constants import AlertSeverity, AlertTriggerType, ScopeType
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class AlertRule(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "alert_rules"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_type: Mapped[str] = mapped_column(
        SAEnum(AlertTriggerType, name="alert_trigger_type_enum"),
        nullable=False,
    )
    condition: Mapped[str] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        SAEnum(AlertSeverity, name="alert_severity_enum"),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(
        SAEnum(ScopeType, name="scope_type_enum", create_type=False),
        nullable=True,
    )
    scope_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
