import uuid
from typing import List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.role_permission import RolePermission
from src.app.repositories.base import BaseRepository


class RolePermissionRepository(BaseRepository[RolePermission]):
    def __init__(self, db: AsyncSession):
        super().__init__(RolePermission, db)

    async def get_by_role_id(self, role_id: uuid.UUID) -> List[RolePermission]:
        result = await self.db.execute(
            select(RolePermission).where(RolePermission.role_id == role_id)
        )
        return list(result.scalars().all())

    async def delete_by_role_id(self, role_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(RolePermission).where(RolePermission.role_id == role_id)
        )
        await self.db.flush()
