import uuid
from typing import Optional

from src.app.repositories.notification_log import NotificationLogRepository
from src.app.schemas.notification_log import InAppNotificationResponse


class NotificationService:
    def __init__(self, notif_repo: NotificationLogRepository):
        self.notif_repo = notif_repo

    async def get_user_notifications(
        self,
        user_id: uuid.UUID,
        is_read: Optional[bool] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[InAppNotificationResponse]:
        logs = await self.notif_repo.get_user_in_app(user_id, is_read, skip, limit)
        return [self._to_response(log) for log in logs]

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        return await self.notif_repo.get_unread_count(user_id)

    async def get_total_count(
        self, user_id: uuid.UUID, is_read: Optional[bool] = None
    ) -> int:
        return await self.notif_repo.count_user_in_app(user_id, is_read)

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return await self.notif_repo.mark_read(notification_id, user_id)

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        return await self.notif_repo.mark_all_read(user_id)

    @staticmethod
    def _to_response(log) -> InAppNotificationResponse:
        alert = log.alert_event
        return InAppNotificationResponse(
            id=log.id,
            alert_event_id=log.alert_event_id,
            severity=alert.severity if alert else "MEDIUM",
            message=alert.message if alert else "",
            is_read=log.is_read,
            sent_at=log.sent_at,
            read_at=log.read_at,
            device_id=str(alert.device_id) if alert and alert.device_id else None,
            location_name=(
                alert.location.name
                if alert and alert.location
                else None
            ),
        )
