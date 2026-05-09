import uuid
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import AlertStatus
from src.app.models.alert_event import AlertEvent
from src.app.repositories.base import BaseRepository


class AlertEventRepository(BaseRepository[AlertEvent]):
    def __init__(self, db: AsyncSession):
        super().__init__(AlertEvent, db)

    async def get_active(self, limit: int = 50) -> List[AlertEvent]:
        result = await self.db.execute(
            select(AlertEvent)
            .where(AlertEvent.status == AlertStatus.ACTIVE)
            .order_by(AlertEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_location_id(
        self, location_id: uuid.UUID, status: Optional[AlertStatus] = None
    ) -> List[AlertEvent]:
        query = select(AlertEvent).where(AlertEvent.location_id == location_id)
        if status:
            query = query.where(AlertEvent.status == status)
        query = query.order_by(AlertEvent.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]],
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[AlertEvent]:
        query = select(AlertEvent)
        if location_ids is not None:
            query = query.where(AlertEvent.location_id.in_(location_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(AlertEvent, key):
                    query = query.where(getattr(AlertEvent, key) == value)
        query = query.order_by(AlertEvent.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]],
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        query = select(func.count()).select_from(AlertEvent)
        if location_ids is not None:
            query = query.where(AlertEvent.location_id.in_(location_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(AlertEvent, key):
                    query = query.where(getattr(AlertEvent, key) == value)
        result = await self.db.execute(query)
        return result.scalar_one()
