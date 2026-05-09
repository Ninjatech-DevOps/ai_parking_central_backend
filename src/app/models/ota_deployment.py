from datetime import datetime

from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.core.constants import OTAStatus, RolloutStrategy
from src.app.db.base import Base, UUIDMixin, TimestampMixin


class OTADeployment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ota_deployments"

    target_image: Mapped[str] = mapped_column(String(200), nullable=False)
    previous_image: Mapped[str] = mapped_column(String(200), nullable=True)
    strategy: Mapped[str] = mapped_column(
        SAEnum(RolloutStrategy, name="rollout_strategy_enum"),
        nullable=False,
        default=RolloutStrategy.ROLLING,
    )
    status: Mapped[str] = mapped_column(
        SAEnum(OTAStatus, name="ota_status_enum"),
        nullable=False,
        default=OTAStatus.PENDING,
    )
    total_devices: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auto_rollback: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rollback_threshold_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )
    deployed_by: Mapped["UUID"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    deployer = relationship("User", lazy="selectin")
