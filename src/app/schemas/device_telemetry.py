import uuid
from datetime import datetime
from typing import Optional

from src.app.schemas.base import BaseSchema


class DeviceTelemetryCreate(BaseSchema):
    device_id: uuid.UUID
    cpu_percent: Optional[float] = None
    temperature: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    uptime_seconds: Optional[float] = None


class DeviceTelemetryResponse(BaseSchema):
    id: uuid.UUID
    device_id: uuid.UUID
    cpu_percent: Optional[float]
    temperature: Optional[float]
    memory_percent: Optional[float]
    disk_percent: Optional[float]
    uptime_seconds: Optional[float]
    recorded_at: datetime
