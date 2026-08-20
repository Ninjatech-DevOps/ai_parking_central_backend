"""Pydantic schemas for the vehicle counter module."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import Field

from src.app.schemas.base import BaseSchema


class LoginRequest(BaseSchema):
    """Single shared password -- there is no username."""

    password: str


class RefreshRequest(BaseSchema):
    refresh_token: str


class LoginResponse(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    # Access token lifetime in seconds, so the client can refresh ahead of it.
    expires_in: int


VehicleType = Literal["CAR", "TWO_WHEELER"]


class VehicleEventCreate(BaseSchema):
    """Payload for one button press.

    ``in_count`` / ``out_count`` are intentionally absent -- they are derived
    from ``direction`` server-side.
    """

    direction: Literal["IN", "OUT"]
    vehicle_type: VehicleType
    # Normally omitted so the server stamps the time; accepted for backfilling.
    timestamp: Optional[datetime] = None


class VehicleEventUpdate(BaseSchema):
    """Partial update from the records page.

    Consumed with ``model_dump(exclude_unset=True)`` so an omitted field is
    distinguishable from one explicitly set to null -- that is what allows a
    number plate to be cleared.
    """

    direction: Optional[Literal["IN", "OUT"]] = None
    vehicle_type: Optional[VehicleType] = None
    number_plate: Optional[str] = Field(None, max_length=30)
    timestamp: Optional[datetime] = None


class VehicleEventResponse(BaseSchema):
    id: int
    direction: str
    vehicle_type: str
    in_count: int
    out_count: int
    number_plate: Optional[str]
    timestamp: datetime
    created_at: datetime
    updated_at: datetime


class TypeStats(BaseSchema):
    total_in: int
    total_out: int
    currently_inside: int


class VehicleCounterStats(BaseSchema):
    """Per-type figures, plus a combined block so nothing re-adds them."""

    car: TypeStats
    two_wheeler: TypeStats
    overall: TypeStats


class CounterPageData(BaseSchema):
    """Everything the counter page needs, in a single round-trip.

    Keeps the stat tiles and the recent list mutually consistent, and halves
    the request count on the tap-heavy page.
    """

    stats: VehicleCounterStats
    recent: List[VehicleEventResponse]
