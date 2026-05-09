import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.zone import Zone
from src.app.repositories.base import BaseRepository


class ZoneRepository(BaseRepository[Zone]):
    def __init__(self, db: AsyncSession):
        super().__init__(Zone, db)

    async def get_by_floor_id(self, floor_id: uuid.UUID) -> List[Zone]:
        result = await self.db.execute(
            select(Zone).where(Zone.floor_id == floor_id)
        )
        return list(result.scalars().all())
