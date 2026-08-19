"""Vehicle counter ORM model.

Registered on ``VCBase`` (SQLite), never on the shared Postgres ``Base``.
Must not be imported from ``src/app/models/__init__.py``.
"""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.app.vehicle_counter.db import VCBase


class VehicleEvent(VCBase):
    """One row per button press -- an event log, not a running counter.

    Totals are derived with ``SUM(in_count)`` / ``SUM(out_count)``, and
    "currently inside" is the difference between them.

    ``direction`` is the source of truth; ``in_count`` and ``out_count`` are
    always derived from it server-side (see ``service._counts_for``) and are
    never accepted from a client.
    """

    __tablename__ = "vehicle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    direction: Mapped[str] = mapped_column(String(3), nullable=False)  # "IN" | "OUT"
    in_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    out_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Optional -- left empty at tap time, filled in later from the records page.
    number_plate: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Server-set on create, editable afterwards.
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Soft delete: rows are never removed. A non-null value hides the row from
    # every listing and from the IN/OUT totals, but the record stays in the
    # database for audit and can be recovered by clearing this column.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "direction IN ('IN','OUT')",
            name="ck_vehicle_events_direction",
        ),
        # Backstop for the core invariant, enforced on INSERT and UPDATE alike,
        # so a service-layer bug cannot persist an inconsistent row.
        CheckConstraint(
            "(direction = 'IN'  AND in_count = 1 AND out_count = 0) OR "
            "(direction = 'OUT' AND in_count = 0 AND out_count = 1)",
            name="ck_vehicle_events_counts_match_direction",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<VehicleEvent id={self.id} {self.direction} at {self.timestamp}>"
