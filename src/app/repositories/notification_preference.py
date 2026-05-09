import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.notification_preference import NotificationPreference
from src.app.repositories.base import BaseRepository


class NotificationPreferenceRepository(BaseRepository[NotificationPreference]):
    def __init__(self, db: AsyncSession):
        super().__init__(NotificationPreference, db)

    async def get_by_user_id(
        self, user_id: uuid.UUID
    ) -> List[NotificationPreference]:
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
        )
        return list(result.scalars().all())

    async def delete_by_user_id(self, user_id: uuid.UUID) -> None:
        from sqlalchemy import delete
        await self.db.execute(
            delete(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
        )
        await self.db.flush()
