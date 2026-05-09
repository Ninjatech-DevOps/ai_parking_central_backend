import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.location import LocationRepository


class LocationService:
    def __init__(self, location_repo: LocationRepository):
        self.location_repo = location_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        return await self.location_repo.create(data)

    async def get(self, location_id: uuid.UUID) -> Any:
        location = await self.location_repo.get_by_id(location_id)
        if not location:
            raise NotFoundException(detail="Location not found")
        return location

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.location_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.location_repo.count(filters=filters)

    async def get_by_area_id(self, area_id: uuid.UUID) -> List[Any]:
        return await self.location_repo.get_by_area_id(area_id)

    async def update(self, location_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        location = await self.location_repo.get_by_id(location_id)
        if not location:
            raise NotFoundException(detail="Location not found")
        return await self.location_repo.update(location_id, data)

    async def delete(self, location_id: uuid.UUID) -> bool:
        location = await self.location_repo.get_by_id(location_id)
        if not location:
            raise NotFoundException(detail="Location not found")
        return await self.location_repo.delete(location_id)
