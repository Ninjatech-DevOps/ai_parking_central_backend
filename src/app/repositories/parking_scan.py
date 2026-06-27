import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.parking_scan import ParkingScan
from src.app.repositories.base import BaseRepository


class ParkingScanRepository(BaseRepository[ParkingScan]):
    def __init__(self, db: AsyncSession):
        super().__init__(ParkingScan, db)

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 20,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[ParkingScan]:
        query = select(ParkingScan)
        query = self._apply_filters(query, location_id, location_ids, start_date, end_date)
        query = query.order_by(ParkingScan.recorded_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        query = select(func.count()).select_from(ParkingScan)
        query = self._apply_filters(query, location_id, location_ids, start_date, end_date)
        result = await self.db.execute(query)
        return result.scalar_one()

    def _apply_filters(self, query, location_id, location_ids, start_date, end_date):
        if location_id:
            query = query.where(ParkingScan.location_id == location_id)
        elif location_ids is not None:
            query = query.where(ParkingScan.location_id.in_(location_ids))
        if start_date:
            query = query.where(ParkingScan.recorded_at >= start_date)
        if end_date:
            query = query.where(ParkingScan.recorded_at <= end_date)
        return query
