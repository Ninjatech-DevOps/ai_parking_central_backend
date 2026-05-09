import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.taluka import TalukaRepository


class TalukaService:
    def __init__(self, taluka_repo: TalukaRepository):
        self.taluka_repo = taluka_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        return await self.taluka_repo.create(data)

    async def get(self, taluka_id: uuid.UUID) -> Any:
        taluka = await self.taluka_repo.get_by_id(taluka_id)
        if not taluka:
            raise NotFoundException(detail="Taluka not found")
        return taluka

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.taluka_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.taluka_repo.count(filters=filters)

    async def get_by_city_id(self, city_id: uuid.UUID) -> List[Any]:
        return await self.taluka_repo.get_by_city_id(city_id)

    async def update(self, taluka_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        taluka = await self.taluka_repo.get_by_id(taluka_id)
        if not taluka:
            raise NotFoundException(detail="Taluka not found")
        return await self.taluka_repo.update(taluka_id, data)

    async def delete(self, taluka_id: uuid.UUID) -> bool:
        taluka = await self.taluka_repo.get_by_id(taluka_id)
        if not taluka:
            raise NotFoundException(detail="Taluka not found")
        return await self.taluka_repo.delete(taluka_id)
