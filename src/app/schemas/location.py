import uuid
from typing import Optional

from src.app.core.constants import LocationType
from src.app.schemas.base import BaseSchema, BaseResponse


class LocationCreate(BaseSchema):
    name: str
    city_id: uuid.UUID
    area_id: Optional[uuid.UUID] = None
    taluka_id: Optional[uuid.UUID] = None
    village_id: Optional[uuid.UUID] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_type: LocationType = LocationType.OPEN
    total_capacity: int = 0
    total_car_slots: int = 0
    total_two_wheeler_slots: int = 0


class LocationUpdate(BaseSchema):
    name: Optional[str] = None
    area_id: Optional[uuid.UUID] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_type: Optional[LocationType] = None
    total_capacity: Optional[int] = None
    total_car_slots: Optional[int] = None
    total_two_wheeler_slots: Optional[int] = None
    is_active: Optional[bool] = None


class LocationResponse(BaseResponse):
    name: str
    area_id: Optional[uuid.UUID]
    city_id: Optional[uuid.UUID]
    taluka_id: Optional[uuid.UUID]
    village_id: Optional[uuid.UUID]
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    location_type: str
    total_capacity: int
    total_car_slots: int = 0
    total_two_wheeler_slots: int = 0
    is_active: bool
