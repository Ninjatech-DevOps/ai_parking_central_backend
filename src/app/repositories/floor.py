import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.floor import Floor
from src.app.repositories.base import BaseRepository


class FloorRepository(BaseRepository[Floor]):
    def __init__(self, db: AsyncSession):
        super().__init__(Floor, db)

    async def get_by_location_id(self, location_id: uuid.UUID) -> List[Floor]:
        result = await self.db.execute(
            select(Floor)
            .where(Floor.location_id == location_id)
            .order_by(Floor.level_number)
        )
        return list(result.scalars().all())
