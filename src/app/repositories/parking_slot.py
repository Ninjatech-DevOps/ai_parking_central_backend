import uuid
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import SlotState
from src.app.models.parking_slot import ParkingSlot
from src.app.models.zone import Zone
from src.app.models.floor import Floor
from src.app.repositories.base import BaseRepository


class ParkingSlotRepository(BaseRepository[ParkingSlot]):
    def __init__(self, db: AsyncSession):
        super().__init__(ParkingSlot, db)

    async def get_by_zone_id(self, zone_id: uuid.UUID) -> List[ParkingSlot]:
        result = await self.db.execute(
            select(ParkingSlot).where(ParkingSlot.zone_id == zone_id)
        )
        return list(result.scalars().all())

    async def count_by_state(self, zone_id: uuid.UUID) -> dict:
        result = await self.db.execute(
            select(ParkingSlot.state, func.count())
            .where(ParkingSlot.zone_id == zone_id)
            .group_by(ParkingSlot.state)
        )
        return {row[0]: row[1] for row in result.all()}

    async def update_state(
        self, slot_id: uuid.UUID, state: SlotState
    ) -> ParkingSlot:
        return await self.update(slot_id, {"state": state})

    async def get_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]],
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ParkingSlot]:
        query = select(ParkingSlot)
        if location_ids is not None:
            query = query.join(Zone, Zone.id == ParkingSlot.zone_id).join(
                Floor, Floor.id == Zone.floor_id
            ).where(Floor.location_id.in_(location_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(ParkingSlot, key):
                    query = query.where(getattr(ParkingSlot, key) == value)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]],
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        query = select(func.count()).select_from(ParkingSlot)
        if location_ids is not None:
            query = query.join(Zone, Zone.id == ParkingSlot.zone_id).join(
                Floor, Floor.id == Zone.floor_id
            ).where(Floor.location_id.in_(location_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(ParkingSlot, key):
                    query = query.where(getattr(ParkingSlot, key) == value)
        result = await self.db.execute(query)
        return result.scalar_one()
