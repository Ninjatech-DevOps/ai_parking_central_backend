import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set

from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.anpr_record import AnprRecord
from src.app.models.location import Location
from src.app.repositories.base import BaseRepository


class AnprRecordRepository(BaseRepository[AnprRecord]):
    def __init__(self, db: AsyncSession):
        super().__init__(AnprRecord, db)

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 20,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        direction: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AnprRecord]:
        query = select(AnprRecord)
        query = self._apply_filters(query, location_id, location_ids, number_plate, vehicle_type, direction, start_date, end_date)
        query = query.order_by(AnprRecord.recorded_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        direction: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        query = select(func.count()).select_from(AnprRecord)
        query = self._apply_filters(query, location_id, location_ids, number_plate, vehicle_type, direction, start_date, end_date)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def search_plates(
        self,
        query_str: str,
        location_ids: Optional[Set[uuid.UUID]] = None,
        limit: int = 10,
    ) -> List[str]:
        """Autocomplete: return distinct plates matching prefix."""
        query = (
            select(distinct(AnprRecord.number_plate))
            .where(AnprRecord.number_plate.ilike(f"%{query_str}%"))
            .order_by(AnprRecord.number_plate)
            .limit(limit)
        )
        if location_ids is not None:
            query = query.where(AnprRecord.location_id.in_(location_ids))
        result = await self.db.execute(query)
        return [row[0] for row in result.all()]

    def _apply_filters(self, query, location_id, location_ids, number_plate, vehicle_type, direction, start_date, end_date):
        if location_id:
            query = query.where(AnprRecord.location_id == location_id)
        elif location_ids is not None:
            query = query.where(AnprRecord.location_id.in_(location_ids))
        if number_plate:
            query = query.where(AnprRecord.number_plate.ilike(f"%{number_plate}%"))
        if vehicle_type:
            query = query.where(AnprRecord.vehicle_type == vehicle_type)
        if direction:
            query = query.where(AnprRecord.direction == direction)
        if start_date:
            query = query.where(AnprRecord.recorded_at >= start_date)
        if end_date:
            query = query.where(AnprRecord.recorded_at <= end_date)
        return query
