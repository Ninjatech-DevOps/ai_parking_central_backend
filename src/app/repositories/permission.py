from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.permission import Permission
from src.app.repositories.base import BaseRepository


class PermissionRepository(BaseRepository[Permission]):
    def __init__(self, db: AsyncSession):
        super().__init__(Permission, db)

    async def get_by_key(self, resource: str, action: str) -> Optional[Permission]:
        result = await self.db.execute(
            select(Permission).where(
                Permission.resource == resource,
                Permission.action == action,
            )
        )
        return result.scalars().first()

    async def get_by_resource(self, resource: str) -> List[Permission]:
        result = await self.db.execute(
            select(Permission).where(Permission.resource == resource)
        )
        return list(result.scalars().all())
