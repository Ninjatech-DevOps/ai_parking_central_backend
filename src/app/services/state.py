import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import ConflictException, NotFoundException
from src.app.repositories.state import StateRepository


class StateService:
    def __init__(self, state_repo: StateRepository):
        self.state_repo = state_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        existing = await self.state_repo.get_by_code(data["code"])
        if existing:
            raise ConflictException(detail="State code already exists")
        return await self.state_repo.create(data)

    async def get(self, state_id: uuid.UUID) -> Any:
        state = await self.state_repo.get_by_id(state_id)
        if not state:
            raise NotFoundException(detail="State not found")
        return state

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.state_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.state_repo.count(filters=filters)

    async def update(self, state_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        state = await self.state_repo.get_by_id(state_id)
        if not state:
            raise NotFoundException(detail="State not found")
        return await self.state_repo.update(state_id, data)

    async def delete(self, state_id: uuid.UUID) -> bool:
        state = await self.state_repo.get_by_id(state_id)
        if not state:
            raise NotFoundException(detail="State not found")
        return await self.state_repo.delete(state_id)
