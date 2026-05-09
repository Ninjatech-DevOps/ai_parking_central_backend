import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.floor import FloorRepository


class FloorService:
    def __init__(self, floor_repo: FloorRepository):
        self.floor_repo = floor_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        return await self.floor_repo.create(data)

    async def get(self, floor_id: uuid.UUID) -> Any:
        floor = await self.floor_repo.get_by_id(floor_id)
        if not floor:
            raise NotFoundException(detail="Floor not found")
        return floor

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.floor_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.floor_repo.count(filters=filters)

    async def get_by_location_id(self, location_id: uuid.UUID) -> List[Any]:
        return await self.floor_repo.get_by_location_id(location_id)

    async def update(self, floor_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        floor = await self.floor_repo.get_by_id(floor_id)
        if not floor:
            raise NotFoundException(detail="Floor not found")
        return await self.floor_repo.update(floor_id, data)

    async def delete(self, floor_id: uuid.UUID) -> bool:
        floor = await self.floor_repo.get_by_id(floor_id)
        if not floor:
            raise NotFoundException(detail="Floor not found")
        return await self.floor_repo.delete(floor_id)
