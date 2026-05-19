import uuid
from datetime import datetime
from typing import Optional

from src.app.core.constants import NotificationChannel
from src.app.schemas.base import BaseSchema


class NotificationLogCreate(BaseSchema):
    user_id: uuid.UUID
    alert_event_id: uuid.UUID
    channel: NotificationChannel


class NotificationLogResponse(BaseSchema):
    id: uuid.UUID
    user_id: uuid.UUID
    alert_event_id: uuid.UUID
    channel: str
    status: str
    sent_at: datetime
    error: Optional[str]
    is_read: bool
    read_at: Optional[datetime]


class InAppNotificationResponse(BaseSchema):
    """Response for in-app notification bell/list."""
    id: uuid.UUID
    alert_event_id: uuid.UUID
    severity: str
    message: str
    is_read: bool
    sent_at: datetime
    read_at: Optional[datetime]
    device_id: Optional[str]
    location_name: Optional[str]
