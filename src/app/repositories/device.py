import uuid
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import DeviceStatus
from src.app.models.device import Device
from src.app.repositories.base import BaseRepository


class DeviceRepository(BaseRepository[Device]):
    def __init__(self, db: AsyncSession):
        super().__init__(Device, db)

    async def get_by_device_id(self, device_id: str) -> Optional[Device]:
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        return result.scalars().first()

    async def get_by_location_id(self, location_id: uuid.UUID) -> List[Device]:
        result = await self.db.execute(
            select(Device).where(Device.location_id == location_id)
        )
        return list(result.scalars().all())

    async def get_by_status(self, status: DeviceStatus) -> List[Device]:
        result = await self.db.execute(
            select(Device).where(Device.status == status)
        )
        return list(result.scalars().all())

    async def get_by_location_ids(self, location_ids: List[uuid.UUID]) -> List[Device]:
        result = await self.db.execute(
            select(Device).where(Device.location_id.in_(location_ids))
        )
        return list(result.scalars().all())

    async def get_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]],
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Device]:
        query = select(Device)
        if location_ids is not None:
            query = query.where(Device.location_id.in_(location_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(Device, key):
                    query = query.where(getattr(Device, key) == value)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]],
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        query = select(func.count()).select_from(Device)
        if location_ids is not None:
            query = query.where(Device.location_id.in_(location_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(Device, key):
                    query = query.where(getattr(Device, key) == value)
        result = await self.db.execute(query)
        return result.scalar_one()
