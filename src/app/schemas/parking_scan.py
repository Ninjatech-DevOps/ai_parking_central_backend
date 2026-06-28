import uuid
from datetime import datetime
from typing import Optional

from src.app.schemas.base import BaseSchema


class ParkingScanResponse(BaseSchema):
    id: uuid.UUID
    device_id: uuid.UUID
    camera_id: uuid.UUID
    location_id: uuid.UUID
    city_id: Optional[uuid.UUID]
    image_url: Optional[str]
    car_occupied: int
    car_available: int
    car_total: int
    two_wheeler_occupied: int
    two_wheeler_available: int
    two_wheeler_total: int
    has_obstruction: bool
    recorded_at: datetime
    location_name: Optional[str] = None
    camera_label: Optional[str] = None
    device_name: Optional[str] = None

    model_config = {"from_attributes": True}
