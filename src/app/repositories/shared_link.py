import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.shared_link import SharedLink
from src.app.repositories.base import BaseRepository


class SharedLinkRepository(BaseRepository[SharedLink]):
    def __init__(self, db: AsyncSession):
        super().__init__(SharedLink, db)

    async def get_by_token(self, token: str) -> Optional[SharedLink]:
        result = await self.db.execute(
            select(SharedLink).where(SharedLink.token == token)
        )
        return result.scalars().first()

    async def search(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SharedLink]:
        query = select(SharedLink)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    SharedLink.name.ilike(pattern),
                    SharedLink.token.ilike(pattern),
                )
            )
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(SharedLink, key):
                    query = query.where(getattr(SharedLink, key) == value)
        query = query.order_by(SharedLink.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_search(
        self,
        search: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        query = select(func.count()).select_from(SharedLink)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    SharedLink.name.ilike(pattern),
                    SharedLink.token.ilike(pattern),
                )
            )
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(SharedLink, key):
                    query = query.where(getattr(SharedLink, key) == value)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def increment_view_count(self, link_id: uuid.UUID) -> None:
        link = await self.get_by_id(link_id)
        if link:
            await self.update(link_id, {"view_count": link.view_count + 1})
