import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.area import Area
from src.app.repositories.base import BaseRepository


class AreaRepository(BaseRepository[Area]):
    def __init__(self, db: AsyncSession):
        super().__init__(Area, db)

    async def get_by_city_id(self, city_id: uuid.UUID) -> List[Area]:
        result = await self.db.execute(
            select(Area).where(Area.city_id == city_id)
        )
        return list(result.scalars().all())
