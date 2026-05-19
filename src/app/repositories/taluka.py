import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.taluka import Taluka
from src.app.repositories.base import BaseRepository


class TalukaRepository(BaseRepository[Taluka]):
    def __init__(self, db: AsyncSession):
        super().__init__(Taluka, db)

    async def get_by_city_id(self, city_id: uuid.UUID) -> List[Taluka]:
        result = await self.db.execute(
            select(Taluka).where(Taluka.city_id == city_id)
            .order_by(Taluka.name)
        )
        return list(result.scalars().all())
