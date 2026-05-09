import uuid
from datetime import datetime
from typing import Optional

from src.app.core.constants import DeviceStatus
from src.app.schemas.base import BaseSchema, BaseResponse


class DeviceCreate(BaseSchema):
    device_id: str
    location_id: uuid.UUID
    zone_id: Optional[uuid.UUID] = None
    ip_address: Optional[str] = None
    docker_image_version: Optional[str] = None


class DeviceUpdate(BaseSchema):
    location_id: Optional[uuid.UUID] = None
    zone_id: Optional[uuid.UUID] = None
    status: Optional[DeviceStatus] = None
    ip_address: Optional[str] = None
    docker_image_version: Optional[str] = None


class DeviceResponse(BaseResponse):
    device_id: str
    location_id: uuid.UUID
    zone_id: Optional[uuid.UUID]
    status: str
    ip_address: Optional[str]
    docker_image_version: Optional[str]
    last_seen: Optional[datetime]


class DeviceFilter(BaseSchema):
    location_id: Optional[uuid.UUID] = None
    zone_id: Optional[uuid.UUID] = None
    status: Optional[DeviceStatus] = None
    device_id: Optional[str] = None
