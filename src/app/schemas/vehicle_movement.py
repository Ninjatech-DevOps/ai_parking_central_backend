import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import Field

from src.app.core.constants import MovementDirection, VehicleType
from src.app.schemas.base import BaseResponse, BaseSchema


class VehicleMovementCreate(BaseSchema):
    location_id: uuid.UUID
    direction: MovementDirection
    vehicle_type: VehicleType = VehicleType.CAR
    camera_id: Optional[uuid.UUID] = None
    device_id: Optional[uuid.UUID] = None
    number_plate: Optional[str] = Field(default=None, max_length=30)
    # Omit to stamp "now" server-side. Supplied when a device is replaying
    # movements it buffered while offline.
    recorded_at: Optional[datetime] = None


class VehicleMovementUpdate(BaseSchema):
    direction: Optional[MovementDirection] = None
    vehicle_type: Optional[VehicleType] = None
    number_plate: Optional[str] = Field(default=None, max_length=30)
    recorded_at: Optional[datetime] = None


class VehicleMovementResponse(BaseResponse):
    location_id: uuid.UUID
    location_name: Optional[str] = None
    camera_id: Optional[uuid.UUID] = None
    camera_label: Optional[str] = None
    device_id: Optional[uuid.UUID] = None
    vehicle_type: str
    direction: str
    number_plate: Optional[str] = None
    recorded_at: datetime

    # Rendered straight into the In / Out columns. Derived from direction so a
    # row can never claim to be both, and so the frontend never has to know how
    # the two columns relate.
    in_count: int = 0
    out_count: int = 0


class VehicleMovementSummary(BaseSchema):
    """Totals for the whole filtered window, not just the current page."""

    total_in: int = 0
    total_out: int = 0
    # in − out over the window. Negative means more vehicles left than entered,
    # which is normal for a window that opens mid-day.
    net: int = 0


class VehicleMovementListResponse(BaseSchema):
    items: List[VehicleMovementResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    summary: VehicleMovementSummary


def build_movement_response(
    movement,
    location_name: Optional[str] = None,
    camera_label: Optional[str] = None,
) -> VehicleMovementResponse:
    """Map one ORM row plus its joined labels onto the response shape."""
    resp = VehicleMovementResponse.model_validate(movement)
    resp.location_name = location_name
    resp.camera_label = camera_label
    is_in = movement.direction == MovementDirection.IN.value
    resp.in_count = 1 if is_in else 0
    resp.out_count = 0 if is_in else 1
    return resp
