import uuid
from typing import List, Optional

from src.app.core.constants import SlotState
from src.app.schemas.base import BaseSchema, BaseResponse


class ParkingSlotCreate(BaseSchema):
    label: str
    zone_id: uuid.UUID
    camera_id: Optional[uuid.UUID] = None
    state: SlotState = SlotState.EMPTY
    polygon_coords: Optional[str] = None
    pos_x1: Optional[int] = None
    pos_y1: Optional[int] = None
    pos_x2: Optional[int] = None
    pos_y2: Optional[int] = None


class ParkingSlotUpdate(BaseSchema):
    label: Optional[str] = None
    camera_id: Optional[uuid.UUID] = None
    state: Optional[SlotState] = None
    polygon_coords: Optional[str] = None
    pos_x1: Optional[int] = None
    pos_y1: Optional[int] = None
    pos_x2: Optional[int] = None
    pos_y2: Optional[int] = None


class ParkingSlotResponse(BaseResponse):
    label: str
    zone_id: uuid.UUID
    camera_id: Optional[uuid.UUID]
    state: str
    polygon_coords: Optional[str]
    pos_x1: Optional[int]
    pos_y1: Optional[int]
    pos_x2: Optional[int]
    pos_y2: Optional[int]


class ParkingSlotFilter(BaseSchema):
    zone_id: Optional[uuid.UUID] = None
    camera_id: Optional[uuid.UUID] = None
    state: Optional[SlotState] = None
