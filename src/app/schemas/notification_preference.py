import uuid
from typing import Optional

from src.app.core.constants import AlertSeverity, NotificationChannel
from src.app.schemas.base import BaseSchema, BaseResponse


class NotificationPreferenceCreate(BaseSchema):
    user_id: uuid.UUID
    alert_severity: AlertSeverity
    channel: NotificationChannel
    is_enabled: bool = True


class NotificationPreferenceUpdate(BaseSchema):
    is_enabled: Optional[bool] = None


class NotificationPreferenceResponse(BaseResponse):
    user_id: uuid.UUID
    alert_severity: str
    channel: str
    is_enabled: bool


class NotificationPreferenceBulkItem(BaseSchema):
    alert_severity: AlertSeverity
    channel: NotificationChannel
    is_enabled: bool


class NotificationPreferenceBulkUpdate(BaseSchema):
    """Set all preferences at once. Replaces existing preferences for this user."""
    preferences: list[NotificationPreferenceBulkItem]
