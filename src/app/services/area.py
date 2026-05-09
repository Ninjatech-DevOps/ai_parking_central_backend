import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.area import AreaRepository


class AreaService:
    def __init__(self, area_repo: AreaRepository):
        self.area_repo = area_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        return await self.area_repo.create(data)

    async def get(self, area_id: uuid.UUID) -> Any:
        area = await self.area_repo.get_by_id(area_id)
        if not area:
            raise NotFoundException(detail="Area not found")
        return area

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.area_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.area_repo.count(filters=filters)

    async def get_by_city_id(self, city_id: uuid.UUID) -> List[Any]:
        return await self.area_repo.get_by_city_id(city_id)

    async def update(self, area_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        area = await self.area_repo.get_by_id(area_id)
        if not area:
            raise NotFoundException(detail="Area not found")
        return await self.area_repo.update(area_id, data)

    async def delete(self, area_id: uuid.UUID) -> bool:
        area = await self.area_repo.get_by_id(area_id)
        if not area:
            raise NotFoundException(detail="Area not found")
        return await self.area_repo.delete(area_id)
