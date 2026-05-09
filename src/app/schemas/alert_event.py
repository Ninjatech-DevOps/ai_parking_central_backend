import uuid
from datetime import datetime
from typing import Optional

from src.app.core.constants import AlertSeverity, AlertStatus
from src.app.schemas.base import BaseSchema


class AlertEventCreate(BaseSchema):
    alert_rule_id: uuid.UUID
    device_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    severity: AlertSeverity
    message: str


class AlertEventUpdate(BaseSchema):
    status: Optional[AlertStatus] = None


class AlertEventResponse(BaseSchema):
    id: uuid.UUID
    alert_rule_id: uuid.UUID
    device_id: Optional[uuid.UUID]
    location_id: Optional[uuid.UUID]
    severity: str
    message: str
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[uuid.UUID]
    resolved_at: Optional[datetime]


class AlertEventFilter(BaseSchema):
    severity: Optional[AlertSeverity] = None
    status: Optional[AlertStatus] = None
    device_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
