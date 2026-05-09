import uuid
from typing import Optional

from src.app.core.constants import SlotState
from src.app.schemas.base import BaseSchema, BaseResponse


class ParkingSlotCreate(BaseSchema):
    label: str
    zone_id: uuid.UUID
    state: SlotState = SlotState.EMPTY


class ParkingSlotUpdate(BaseSchema):
    label: Optional[str] = None
    state: Optional[SlotState] = None


class ParkingSlotResponse(BaseResponse):
    label: str
    zone_id: uuid.UUID
    state: str


class ParkingSlotFilter(BaseSchema):
    zone_id: Optional[uuid.UUID] = None
    state: Optional[SlotState] = None
