import uuid
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.camera import Camera
from src.app.models.device import Device
from src.app.repositories.base import BaseRepository


class CameraRepository(BaseRepository[Camera]):
    def __init__(self, db: AsyncSession):
        super().__init__(Camera, db)

    def _scoped_query(self, query, location_ids: Optional[Set[uuid.UUID]]):
        """Restrict to cameras whose device sits in one of these locations.

        A single join — cameras belong to devices, devices to locations. Going
        via devices first and then querying cameras per device would be a 1+N.
        `None` means unrestricted (super admin).
        """
        if location_ids is not None:
            query = query.join(Device, Device.id == Camera.device_id).where(
                Device.location_id.in_(location_ids)
            )
        return query

    @staticmethod
    def _apply_filters(query, filters: Optional[Dict[str, Any]]):
        for key, value in (filters or {}).items():
            if value is not None and hasattr(Camera, key):
                query = query.where(getattr(Camera, key) == value)
        return query

    async def get_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]] = None,
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Camera]:
        query = self._scoped_query(select(Camera), location_ids)
        query = self._apply_filters(query, filters)
        query = query.order_by(Camera.position_label).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_scoped(
        self,
        location_ids: Optional[Set[uuid.UUID]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        query = self._scoped_query(select(func.count()).select_from(Camera), location_ids)
        query = self._apply_filters(query, filters)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def get_by_device_id(self, device_id: uuid.UUID, active_only: bool = True) -> List[Camera]:
        query = select(Camera).where(Camera.device_id == device_id)
        if active_only:
            query = query.where(Camera.is_active == True)
        query = query.order_by(Camera.position_label)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_device_and_label(self, device_id: uuid.UUID, label: str):
        result = await self.db.execute(
            select(Camera).where(
                Camera.device_id == device_id,
                Camera.position_label == label,
            )
        )
        return result.scalars().first()
