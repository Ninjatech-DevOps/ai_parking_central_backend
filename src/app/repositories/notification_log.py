import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.notification_log import NotificationLog
from src.app.repositories.base import BaseRepository


class NotificationLogRepository(BaseRepository[NotificationLog]):
    def __init__(self, db: AsyncSession):
        super().__init__(NotificationLog, db)

    async def get_by_alert_event_id(
        self, alert_event_id: uuid.UUID
    ) -> List[NotificationLog]:
        result = await self.db.execute(
            select(NotificationLog).where(
                NotificationLog.alert_event_id == alert_event_id
            )
        )
        return list(result.scalars().all())
