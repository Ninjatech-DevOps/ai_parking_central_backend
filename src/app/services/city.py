import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.city import CityRepository


class CityService:
    def __init__(self, city_repo: CityRepository):
        self.city_repo = city_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        return await self.city_repo.create(data)

    async def get(self, city_id: uuid.UUID) -> Any:
        city = await self.city_repo.get_by_id(city_id)
        if not city:
            raise NotFoundException(detail="City not found")
        return city

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.city_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.city_repo.count(filters=filters)

    async def get_by_state_id(self, state_id: uuid.UUID) -> List[Any]:
        return await self.city_repo.get_by_state_id(state_id)

    async def update(self, city_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        city = await self.city_repo.get_by_id(city_id)
        if not city:
            raise NotFoundException(detail="City not found")
        return await self.city_repo.update(city_id, data)

    async def delete(self, city_id: uuid.UUID) -> bool:
        city = await self.city_repo.get_by_id(city_id)
        if not city:
            raise NotFoundException(detail="City not found")
        return await self.city_repo.delete(city_id)
