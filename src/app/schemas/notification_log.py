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
