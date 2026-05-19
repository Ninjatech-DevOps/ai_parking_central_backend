import uuid
from datetime import datetime
from typing import Optional

from src.app.core.constants import SlotState
from src.app.schemas.base import BaseSchema


class SlotEventCreate(BaseSchema):
    parking_slot_id: uuid.UUID
    previous_state: Optional[SlotState] = None
    new_state: SlotState
    device_id: Optional[uuid.UUID] = None


class SlotEventResponse(BaseSchema):
    id: uuid.UUID
    parking_slot_id: uuid.UUID
    previous_state: Optional[str]
    new_state: str
    device_id: Optional[uuid.UUID]
    recorded_at: datetime


class ParkingSessionResponse(BaseSchema):
    entry_event_id: str
    slot_id: str
    slot_label: str
    camera_label: Optional[str]
    location_name: Optional[str]
    location_id: Optional[str]
    area_name: Optional[str]
    city_name: Optional[str]
    camera_id: Optional[str]
    event_type: str
    entry_time: str
    exit_time: Optional[str]
    duration_minutes: Optional[float]
    is_active: bool
