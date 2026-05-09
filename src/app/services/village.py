import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.village import VillageRepository


class VillageService:
    def __init__(self, village_repo: VillageRepository):
        self.village_repo = village_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        return await self.village_repo.create(data)

    async def get(self, village_id: uuid.UUID) -> Any:
        village = await self.village_repo.get_by_id(village_id)
        if not village:
            raise NotFoundException(detail="Village not found")
        return village

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.village_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.village_repo.count(filters=filters)

    async def get_by_taluka_id(self, taluka_id: uuid.UUID) -> List[Any]:
        return await self.village_repo.get_by_taluka_id(taluka_id)

    async def update(self, village_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        village = await self.village_repo.get_by_id(village_id)
        if not village:
            raise NotFoundException(detail="Village not found")
        return await self.village_repo.update(village_id, data)

    async def delete(self, village_id: uuid.UUID) -> bool:
        village = await self.village_repo.get_by_id(village_id)
        if not village:
            raise NotFoundException(detail="Village not found")
        return await self.village_repo.delete(village_id)
