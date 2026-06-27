import uuid
from datetime import datetime
from typing import List, Optional, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import VehicleType
from src.app.models.anpr_session import AnprSession
from src.app.repositories.base import BaseRepository


class AnprSessionRepository(BaseRepository[AnprSession]):
    def __init__(self, db: AsyncSession):
        super().__init__(AnprSession, db)

    async def find_active_session(
        self, location_id: uuid.UUID, number_plate: str
    ) -> Optional[AnprSession]:
        result = await self.db.execute(
            select(AnprSession).where(
                AnprSession.location_id == location_id,
                AnprSession.number_plate == number_plate,
                AnprSession.is_active == True,
            )
        )
        return result.scalars().first()

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 20,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AnprSession]:
        query = select(AnprSession)
        query = self._apply_filters(query, location_id, location_ids, number_plate, vehicle_type, is_active, start_date, end_date)
        query = query.order_by(AnprSession.entry_time.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        query = select(func.count()).select_from(AnprSession)
        query = self._apply_filters(query, location_id, location_ids, number_plate, vehicle_type, is_active, start_date, end_date)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def count_active_by_location(
        self,
        location_ids: Optional[Set[uuid.UUID]] = None,
        location_id: Optional[uuid.UUID] = None,
    ) -> List[dict]:
        """Count active sessions grouped by location_id and vehicle_type."""
        query = (
            select(
                AnprSession.location_id,
                AnprSession.vehicle_type,
                func.count().label("count"),
            )
            .where(AnprSession.is_active == True)
            .group_by(AnprSession.location_id, AnprSession.vehicle_type)
        )
        if location_id:
            query = query.where(AnprSession.location_id == location_id)
        elif location_ids is not None:
            query = query.where(AnprSession.location_id.in_(location_ids))
        result = await self.db.execute(query)
        return [{"location_id": r[0], "vehicle_type": r[1], "count": r[2]} for r in result.all()]

    def _apply_filters(self, query, location_id, location_ids, number_plate, vehicle_type, is_active, start_date, end_date):
        if location_id:
            query = query.where(AnprSession.location_id == location_id)
        elif location_ids is not None:
            query = query.where(AnprSession.location_id.in_(location_ids))
        if number_plate:
            query = query.where(AnprSession.number_plate.ilike(f"%{number_plate}%"))
        if vehicle_type:
            query = query.where(AnprSession.vehicle_type == vehicle_type)
        if is_active is not None:
            query = query.where(AnprSession.is_active == is_active)
        if start_date:
            query = query.where(AnprSession.entry_time >= start_date)
        if end_date:
            query = query.where(AnprSession.entry_time <= end_date)
        return query
