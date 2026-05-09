import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.village import Village
from src.app.repositories.base import BaseRepository


class VillageRepository(BaseRepository[Village]):
    def __init__(self, db: AsyncSession):
        super().__init__(Village, db)

    async def get_by_taluka_id(self, taluka_id: uuid.UUID) -> List[Village]:
        result = await self.db.execute(
            select(Village).where(Village.taluka_id == taluka_id)
        )
        return list(result.scalars().all())
