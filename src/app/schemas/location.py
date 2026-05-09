import uuid
from typing import Optional

from src.app.core.constants import LocationType
from src.app.schemas.base import BaseSchema, BaseResponse


class LocationCreate(BaseSchema):
    name: str
    area_id: uuid.UUID
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_type: LocationType = LocationType.OPEN
    total_capacity: int = 0


class LocationUpdate(BaseSchema):
    name: Optional[str] = None
    area_id: Optional[uuid.UUID] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_type: Optional[LocationType] = None
    total_capacity: Optional[int] = None
    is_active: Optional[bool] = None


class LocationResponse(BaseResponse):
    name: str
    area_id: uuid.UUID
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    location_type: str
    total_capacity: int
    is_active: bool


class LocationFilter(BaseSchema):
    name: Optional[str] = None
    area_id: Optional[uuid.UUID] = None
    location_type: Optional[LocationType] = None
    is_active: Optional[bool] = None
