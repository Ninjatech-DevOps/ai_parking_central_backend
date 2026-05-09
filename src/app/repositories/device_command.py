import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.device_command import DeviceCommand
from src.app.repositories.base import BaseRepository


class DeviceCommandRepository(BaseRepository[DeviceCommand]):
    def __init__(self, db: AsyncSession):
        super().__init__(DeviceCommand, db)

    async def get_by_device_id(
        self, device_id: uuid.UUID, limit: int = 20
    ) -> List[DeviceCommand]:
        result = await self.db.execute(
            select(DeviceCommand)
            .where(DeviceCommand.device_id == device_id)
            .order_by(DeviceCommand.sent_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
