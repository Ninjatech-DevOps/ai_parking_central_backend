import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.slot_event import SlotEvent
from src.app.repositories.base import BaseRepository


class SlotEventRepository(BaseRepository[SlotEvent]):
    def __init__(self, db: AsyncSession):
        super().__init__(SlotEvent, db)

    async def get_by_slot_id(
        self,
        parking_slot_id: uuid.UUID,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SlotEvent]:
        query = (
            select(SlotEvent)
            .where(SlotEvent.parking_slot_id == parking_slot_id)
            .order_by(SlotEvent.recorded_at.desc())
            .limit(limit)
        )
        if start_time:
            query = query.where(SlotEvent.recorded_at >= start_time)
        if end_time:
            query = query.where(SlotEvent.recorded_at <= end_time)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_by_slot_id(self, parking_slot_id: uuid.UUID) -> int:
        result = await self.db.execute(
            delete(SlotEvent).where(SlotEvent.parking_slot_id == parking_slot_id)
        )
        await self.db.flush()
        return result.rowcount
