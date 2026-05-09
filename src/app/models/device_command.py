from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import CommandType, CommandStatus
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class DeviceCommand(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "device_commands"

    device_id: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    command_type: Mapped[str] = mapped_column(
        SAEnum(CommandType, name="command_type_enum"),
        nullable=False,
    )
    payload: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum(CommandStatus, name="command_status_enum"),
        nullable=False,
        default=CommandStatus.SENT,
    )
    sent_by: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    device = relationship("Device", lazy="selectin")
    sender = relationship("User", lazy="selectin")
