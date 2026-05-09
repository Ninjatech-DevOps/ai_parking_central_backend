import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.zone import ZoneRepository


class ZoneService:
    def __init__(self, zone_repo: ZoneRepository):
        self.zone_repo = zone_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        return await self.zone_repo.create(data)

    async def get(self, zone_id: uuid.UUID) -> Any:
        zone = await self.zone_repo.get_by_id(zone_id)
        if not zone:
            raise NotFoundException(detail="Zone not found")
        return zone

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.zone_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.zone_repo.count(filters=filters)

    async def get_by_floor_id(self, floor_id: uuid.UUID) -> List[Any]:
        return await self.zone_repo.get_by_floor_id(floor_id)

    async def update(self, zone_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        zone = await self.zone_repo.get_by_id(zone_id)
        if not zone:
            raise NotFoundException(detail="Zone not found")
        return await self.zone_repo.update(zone_id, data)

    async def delete(self, zone_id: uuid.UUID) -> bool:
        zone = await self.zone_repo.get_by_id(zone_id)
        if not zone:
            raise NotFoundException(detail="Zone not found")
        return await self.zone_repo.delete(zone_id)
