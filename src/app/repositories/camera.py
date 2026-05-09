import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.camera import Camera
from src.app.repositories.base import BaseRepository


class CameraRepository(BaseRepository[Camera]):
    def __init__(self, db: AsyncSession):
        super().__init__(Camera, db)

    async def get_by_device_id(self, device_id: uuid.UUID) -> List[Camera]:
        result = await self.db.execute(
            select(Camera).where(Camera.device_id == device_id)
        )
        return list(result.scalars().all())
