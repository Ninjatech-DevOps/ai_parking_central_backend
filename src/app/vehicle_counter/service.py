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


VEHICLE_TYPES = ("CAR", "TWO_WHEELER")


def _normalize_vehicle_type(value: str) -> str:
    """Validate a vehicle type.

    SQLite cannot add a CHECK constraint to the existing table, so this is the
    real enforcement point for rows written to a pre-existing database.
    """
    normalized = (value or "").strip().upper()
    if normalized not in VEHICLE_TYPES:
        raise BadRequestException(
            detail="vehicle_type must be 'CAR' or 'TWO_WHEELER'"
        )
    return normalized


def normalize_type_filter(value: Optional[str]) -> Optional[str]:
    """Normalize an optional vehicle_type *filter*.

    Distinct from ``_normalize_vehicle_type``, which validates a value being
    written: here a missing value and "ALL" both mean "no filter", so a UI can
    send its select value through unchanged.
    """
    if not value:
        return None
    normalized = value.strip().upper()
    if normalized == "ALL":
        return None
    if normalized not in VEHICLE_TYPES:
        raise BadRequestException(
            detail="vehicle_type must be 'CAR' or 'TWO_WHEELER'"
        )
    return normalized


class VehicleEventService:
    def __init__(self, repo: VehicleEventRepository):
        self.repo = repo

    async def record(
        self,
        direction: str,
        vehicle_type: str,
        timestamp: Optional[datetime] = None,
    ) -> VehicleEvent:
        """Log one button press."""
        normalized = (direction or "").strip().upper()
        in_count, out_count = _counts_for(normalized)
        return await self.repo.create(
            {
                "direction": normalized,
                "vehicle_type": _normalize_vehicle_type(vehicle_type),
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

        # A plain editable field, unlike direction: changing the vehicle type
        # never touches in_count/out_count.
        if "vehicle_type" in patch:
            data["vehicle_type"] = _normalize_vehicle_type(patch["vehicle_type"])

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
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        vehicle_type: Optional[str] = None,
    ) -> List[VehicleEvent]:
        """Events for the Excel export, oldest first."""
        if start and end and start > end:
            raise BadRequestException(detail="start_date must be before end_date")
        if vehicle_type:
            vehicle_type = _normalize_vehicle_type(vehicle_type)
        return await self.repo.list_for_export(start, end, vehicle_type)

    async def logs(
        self,
        skip: int,
        limit: int,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        vehicle_type: Optional[str] = None,
    ) -> Tuple[List[VehicleEvent], int]:
        """One page of events, newest first, plus the matching total.

        The total is counted with the *same* filters as the page, or the pager
        would report the unfiltered figure and offer pages that render empty.
        Soft-deleted rows are excluded from both by the repository.
        """
        if start and end and start > end:
            raise BadRequestException(detail="start_date must be before end_date")

        vtype = normalize_type_filter(vehicle_type)
        items = await self.repo.list_paginated(skip, limit, vtype, start, end)
        total = await self.repo.count(vtype, start, end)
        return items, total

    async def stats(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> dict:
        """Per-type figures plus a combined block.

        ``overall`` is computed here so the export totals row and the UI never
        have to re-add the per-type numbers themselves.

        With no bounds this is the all-time total, which is what the operator
        page shows. Bounds narrow it to a window -- and over a window
        ``currently_inside`` is a NET CHANGE in occupancy, not a live count: a
        vehicle that entered before ``start`` and left inside the window
        contributes only its OUT, so the figure can legitimately be negative.
        """
        if start and end and start > end:
            raise BadRequestException(detail="start_date must be before end_date")

        by_type = await self.repo.totals_by_type(start, end)

        def block(total_in: int, total_out: int) -> dict:
            return {
                "total_in": total_in,
                "total_out": total_out,
                "currently_inside": total_in - total_out,
            }

        car_in, car_out = by_type.get("CAR", (0, 0))
        tw_in, tw_out = by_type.get("TWO_WHEELER", (0, 0))
        return {
            "car": block(car_in, car_out),
            "two_wheeler": block(tw_in, tw_out),
            "overall": block(car_in + tw_in, car_out + tw_out),
        }
