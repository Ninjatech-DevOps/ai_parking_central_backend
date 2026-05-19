import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import NotificationChannel
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

    async def get_user_in_app(
        self,
        user_id: uuid.UUID,
        is_read: Optional[bool] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[NotificationLog]:
        query = (
            select(NotificationLog)
            .where(
                NotificationLog.user_id == user_id,
                NotificationLog.channel == NotificationChannel.IN_APP,
            )
            .order_by(NotificationLog.sent_at.desc())
        )
        if is_read is not None:
            query = query.where(NotificationLog.is_read == is_read)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_user_in_app(
        self, user_id: uuid.UUID, is_read: Optional[bool] = None
    ) -> int:
        query = (
            select(func.count())
            .select_from(NotificationLog)
            .where(
                NotificationLog.user_id == user_id,
                NotificationLog.channel == NotificationChannel.IN_APP,
            )
        )
        if is_read is not None:
            query = query.where(NotificationLog.is_read == is_read)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        return await self.count_user_in_app(user_id, is_read=False)

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            update(NotificationLog)
            .where(
                NotificationLog.id == notification_id,
                NotificationLog.user_id == user_id,
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        await self.db.flush()
        return result.rowcount > 0

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            update(NotificationLog)
            .where(
                NotificationLog.user_id == user_id,
                NotificationLog.channel == NotificationChannel.IN_APP,
                NotificationLog.is_read == False,
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        await self.db.flush()
        return result.rowcount
