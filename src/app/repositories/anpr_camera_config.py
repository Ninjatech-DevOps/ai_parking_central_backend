import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.anpr_camera_config import AnprCameraConfig
from src.app.repositories.base import BaseRepository


class AnprCameraConfigRepository(BaseRepository[AnprCameraConfig]):
    def __init__(self, db: AsyncSession):
        super().__init__(AnprCameraConfig, db)

    async def get_by_camera_id(self, camera_id: uuid.UUID) -> Optional[AnprCameraConfig]:
        result = await self.db.execute(
            select(AnprCameraConfig).where(AnprCameraConfig.camera_id == camera_id)
        )
        return result.scalars().first()
