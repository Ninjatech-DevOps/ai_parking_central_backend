import uuid
from datetime import datetime
from typing import Optional

from src.app.core.constants import VehicleType
from src.app.schemas.base import BaseSchema, BaseResponse


class AnprSessionResponse(BaseResponse):
    location_id: uuid.UUID
    city_id: Optional[uuid.UUID]
    number_plate: str
    vehicle_type: str
    entry_record_id: uuid.UUID
    exit_record_id: Optional[uuid.UUID]
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_image_url: Optional[str]
    exit_image_url: Optional[str]
    is_active: bool
    duration_display: Optional[str] = None
    location_name: Optional[str] = None
