import uuid
from typing import List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.user_role import UserRole
from src.app.repositories.base import BaseRepository


class UserRoleRepository(BaseRepository[UserRole]):
    def __init__(self, db: AsyncSession):
        super().__init__(UserRole, db)

    async def get_by_user_id(self, user_id: uuid.UUID) -> List[UserRole]:
        result = await self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_role_id(self, role_id: uuid.UUID) -> List[UserRole]:
        result = await self.db.execute(
            select(UserRole).where(UserRole.role_id == role_id)
        )
        return list(result.scalars().all())

    async def delete_by_user_id(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(UserRole).where(UserRole.user_id == user_id)
        )
        await self.db.flush()
