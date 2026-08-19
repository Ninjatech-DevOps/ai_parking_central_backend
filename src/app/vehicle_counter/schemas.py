"""Pydantic schemas for the vehicle counter module."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import Field

from src.app.schemas.base import BaseSchema


class VehicleEventCreate(BaseSchema):
    """Payload for one button press.

    ``in_count`` / ``out_count`` are intentionally absent -- they are derived
    from ``direction`` server-side.
    """

    direction: Literal["IN", "OUT"]
    # Normally omitted so the server stamps the time; accepted for backfilling.
    timestamp: Optional[datetime] = None


class VehicleEventUpdate(BaseSchema):
    """Partial update from the records page.

    Consumed with ``model_dump(exclude_unset=True)`` so an omitted field is
    distinguishable from one explicitly set to null -- that is what allows a
    number plate to be cleared.
    """

    direction: Optional[Literal["IN", "OUT"]] = None
    number_plate: Optional[str] = Field(None, max_length=30)
    timestamp: Optional[datetime] = None


class VehicleEventResponse(BaseSchema):
    id: int
    direction: str
    in_count: int
    out_count: int
    number_plate: Optional[str]
    timestamp: datetime
    created_at: datetime
    updated_at: datetime


class VehicleCounterStats(BaseSchema):
    total_in: int
    total_out: int
    currently_inside: int


class CounterPageData(BaseSchema):
    """Everything the counter page needs, in a single round-trip.

    Keeps the stat tiles and the recent list mutually consistent, and halves
    the request count on the tap-heavy page.
    """

    stats: VehicleCounterStats
    recent: List[VehicleEventResponse]
