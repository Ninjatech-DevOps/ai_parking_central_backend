from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.state import State
from src.app.repositories.base import BaseRepository


class StateRepository(BaseRepository[State]):
    def __init__(self, db: AsyncSession):
        super().__init__(State, db)

    async def get_by_code(self, code: str) -> Optional[State]:
        result = await self.db.execute(
            select(State).where(State.code == code)
        )
        return result.scalars().first()
