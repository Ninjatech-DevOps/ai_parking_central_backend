import uuid
from typing import List, Optional

from src.app.core.constants import SlotState, SlotType
from src.app.schemas.base import BaseSchema, BaseResponse


class ParkingSlotCreate(BaseSchema):
    label: str
    zone_id: Optional[uuid.UUID] = None
    camera_id: Optional[uuid.UUID] = None
    state: SlotState = SlotState.EMPTY
    slot_type: SlotType = SlotType.GENERAL
    capacity_car: int = 0
    capacity_two_wheeler: int = 0
    polygon_coords: Optional[str] = None
    pos_x1: Optional[int] = None
    pos_y1: Optional[int] = None
    pos_x2: Optional[int] = None
    pos_y2: Optional[int] = None


class ParkingSlotUpdate(BaseSchema):
    label: Optional[str] = None
    camera_id: Optional[uuid.UUID] = None
    state: Optional[SlotState] = None
    slot_type: Optional[SlotType] = None
    capacity_car: Optional[int] = None
    capacity_two_wheeler: Optional[int] = None
    polygon_coords: Optional[str] = None
    pos_x1: Optional[int] = None
    pos_y1: Optional[int] = None
    pos_x2: Optional[int] = None
    pos_y2: Optional[int] = None


class ParkingSlotResponse(BaseResponse):
    label: str
    zone_id: Optional[uuid.UUID] = None
    camera_id: Optional[uuid.UUID] = None
    state: str
    slot_type: str
    capacity_car: int = 0
    capacity_two_wheeler: int = 0
    occupied_car: int = 0
    occupied_two_wheeler: int = 0
    detected_vehicle_type: Optional[str] = None
    polygon_coords: Optional[str]
    pos_x1: Optional[int]
    pos_y1: Optional[int]
    pos_x2: Optional[int]
    pos_y2: Optional[int]


class ParkingSlotFilter(BaseSchema):
    zone_id: Optional[uuid.UUID] = None
    camera_id: Optional[uuid.UUID] = None
    state: Optional[SlotState] = None
    slot_type: Optional[SlotType] = None
