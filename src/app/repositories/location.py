import uuid
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.location import Location
from src.app.repositories.base import BaseRepository


class LocationRepository(BaseRepository[Location]):
    def __init__(self, db: AsyncSession):
        super().__init__(Location, db)

    async def get_by_area_id(self, area_id: uuid.UUID) -> List[Location]:
        result = await self.db.execute(
            select(Location).where(Location.area_id == area_id)
            .order_by(Location.name)
        )
        return list(result.scalars().all())

    async def get_active(self) -> List[Location]:
        result = await self.db.execute(
            select(Location).where(Location.is_active == True)
            .order_by(Location.name)
        )
        return list(result.scalars().all())

    async def get_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]],
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Location]:
        query = select(Location)
        if location_ids is not None:
            query = query.where(Location.id.in_(location_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(Location, key):
                    query = query.where(getattr(Location, key) == value)
        query = query.order_by(Location.name).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]],
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        query = select(func.count()).select_from(Location)
        if location_ids is not None:
            query = query.where(Location.id.in_(location_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(Location, key):
                    query = query.where(getattr(Location, key) == value)
        result = await self.db.execute(query)
        return result.scalar_one()
