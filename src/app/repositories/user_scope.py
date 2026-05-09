import uuid
from typing import List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.user_scope import UserScope
from src.app.repositories.base import BaseRepository


class UserScopeRepository(BaseRepository[UserScope]):
    def __init__(self, db: AsyncSession):
        super().__init__(UserScope, db)

    async def get_by_user_id(self, user_id: uuid.UUID) -> List[UserScope]:
        result = await self.db.execute(
            select(UserScope).where(UserScope.user_id == user_id)
        )
        return list(result.scalars().all())

    async def delete_by_user_id(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(UserScope).where(UserScope.user_id == user_id)
        )
        await self.db.flush()
