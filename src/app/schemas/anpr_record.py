import uuid
from datetime import datetime
from typing import Optional

from src.app.core.constants import AnprDirection, VehicleType
from src.app.schemas.base import BaseSchema


class AnprRecordCreate(BaseSchema):
    device_id: uuid.UUID
    camera_id: uuid.UUID
    location_id: uuid.UUID
    city_id: Optional[uuid.UUID] = None
    number_plate: str
    vehicle_type: VehicleType = VehicleType.CAR
    direction: AnprDirection
    image_url: Optional[str] = None
    gemini_result: Optional[str] = None
    paddle_result: Optional[str] = None
    confidence_gemini: Optional[float] = None
    confidence_paddle: Optional[float] = None
    recorded_at: Optional[datetime] = None


class AnprRecordUpdate(BaseSchema):
    number_plate: Optional[str] = None
    vehicle_type: Optional[VehicleType] = None
    direction: Optional[AnprDirection] = None


class AnprRecordResponse(BaseSchema):
    id: uuid.UUID
    device_id: uuid.UUID
    camera_id: uuid.UUID
    location_id: uuid.UUID
    city_id: Optional[uuid.UUID]
    number_plate: str
    vehicle_type: str
    direction: str
    image_url: Optional[str]
    gemini_result: Optional[str]
    paddle_result: Optional[str]
    confidence_gemini: Optional[float]
    confidence_paddle: Optional[float]
    recorded_at: datetime
    location_name: Optional[str] = None

    model_config = {"from_attributes": True}
