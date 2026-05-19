import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.city import City
from src.app.repositories.base import BaseRepository


class CityRepository(BaseRepository[City]):
    def __init__(self, db: AsyncSession):
        super().__init__(City, db)

    async def get_by_state_id(self, state_id: uuid.UUID) -> List[City]:
        result = await self.db.execute(
            select(City).where(City.state_id == state_id)
            .order_by(City.name)
        )
        return list(result.scalars().all())
