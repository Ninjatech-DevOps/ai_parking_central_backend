"""Business logic for the vehicle counter.

The single rule worth stating plainly: ``direction`` is the source of truth,
and ``in_count`` / ``out_count`` are always derived from it here. Clients never
send counts, so there is exactly one place they can be computed.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from src.app.exceptions.base import BadRequestException, NotFoundException
from src.app.vehicle_counter.models import VehicleEvent
from src.app.vehicle_counter.repository import VehicleEventRepository


def _counts_for(direction: str) -> Tuple[int, int]:
    """Map a direction to ``(in_count, out_count)``."""
    normalized = (direction or "").strip().upper()
    if normalized == "IN":
        return 1, 0
    if normalized == "OUT":
        return 0, 1
    raise BadRequestException(detail="direction must be 'IN' or 'OUT'")


class VehicleEventService:
    def __init__(self, repo: VehicleEventRepository):
        self.repo = repo

    async def record(
        self, direction: str, timestamp: Optional[datetime] = None
    ) -> VehicleEvent:
        """Log one button press."""
        normalized = (direction or "").strip().upper()
        in_count, out_count = _counts_for(normalized)
        return await self.repo.create(
            {
                "direction": normalized,
                "in_count": in_count,
                "out_count": out_count,
                "number_plate": None,
                "timestamp": timestamp or datetime.now(timezone.utc),
            }
        )

    async def update_event(self, event_id: int, patch: dict) -> VehicleEvent:
        """Apply a partial update from the records page.

        ``patch`` comes from ``model_dump(exclude_unset=True)``, so a key being
        present means the client actually sent it -- including an explicit null.
        """
        data: dict = {}

        if "direction" in patch:
            normalized = (patch["direction"] or "").strip().upper()
            in_count, out_count = _counts_for(normalized)  # validates and derives
            data.update(direction=normalized, in_count=in_count, out_count=out_count)

        if "number_plate" in patch:
            plate = patch["number_plate"]
            plate = plate.strip().upper() if isinstance(plate, str) else None
            data["number_plate"] = plate or None  # "" becomes NULL

        if "timestamp" in patch:
            if patch["timestamp"] is None:
                raise BadRequestException(detail="timestamp cannot be null")
            data["timestamp"] = patch["timestamp"]

        if not data:
            raise BadRequestException(detail="No editable fields supplied")

        obj = await self.repo.update(event_id, data)
        if obj is None:
            raise NotFoundException(detail=f"Vehicle event {event_id} not found")
        return obj

    async def delete_event(self, event_id: int) -> None:
        """Soft delete -- the row is hidden everywhere but kept in the database."""
        if not await self.repo.soft_delete(event_id):
            raise NotFoundException(detail=f"Vehicle event {event_id} not found")

    async def export_rows(
        self, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> List[VehicleEvent]:
        """Events for the Excel export, oldest first."""
        if start and end and start > end:
            raise BadRequestException(detail="start_date must be before end_date")
        return await self.repo.list_for_export(start, end)

    async def stats(self) -> dict:
        total_in, total_out = await self.repo.totals()
        return {
            "total_in": total_in,
            "total_out": total_out,
            "currently_inside": total_in - total_out,
        }
