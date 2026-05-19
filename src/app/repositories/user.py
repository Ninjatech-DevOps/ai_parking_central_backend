import uuid
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.user import User
from src.app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalars().first()

    async def get_scoped(
        self,
        visible_user_ids: Optional[Set[uuid.UUID]],
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[User]:
        """
        Fetch users filtered to a set of visible user IDs.
        None = no filter (super admin sees all).
        """
        query = select(User)
        if visible_user_ids is not None:
            query = query.where(User.id.in_(visible_user_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(User, key):
                    query = query.where(getattr(User, key) == value)
        if hasattr(User, "created_at"):
            query = query.order_by(User.created_at)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_scoped(
        self,
        visible_user_ids: Optional[Set[uuid.UUID]],
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        query = select(func.count()).select_from(User)
        if visible_user_ids is not None:
            query = query.where(User.id.in_(visible_user_ids))
        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(User, key):
                    query = query.where(getattr(User, key) == value)
        result = await self.db.execute(query)
        return result.scalar_one()
