import uuid
from typing import Any, Dict, List, Optional

from src.app.core.security import hash_password, verify_password
from src.app.exceptions.base import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from src.app.repositories.user import UserRepository
from src.app.repositories.user_role import UserRoleRepository
from src.app.repositories.user_scope import UserScopeRepository


class UserService:
    def __init__(
        self,
        user_repo: UserRepository,
        user_role_repo: UserRoleRepository,
        user_scope_repo: UserScopeRepository,
    ):
        self.user_repo = user_repo
        self.user_role_repo = user_role_repo
        self.user_scope_repo = user_scope_repo

    async def create_user(self, data: Dict[str, Any]) -> Any:
        existing = await self.user_repo.get_by_email(data["email"])
        if existing:
            raise ConflictException(detail="Email already registered")

        role_ids = data.pop("role_ids", None) or []
        scopes = data.pop("scopes", None) or []
        data["password_hash"] = hash_password(data.pop("password"))

        user = await self.user_repo.create(data)

        for role_id in role_ids:
            await self.user_role_repo.create(
                {"user_id": user.id, "role_id": role_id}
            )

        for scope in scopes:
            await self.user_scope_repo.create(
                {
                    "user_id": user.id,
                    "scope_type": scope["scope_type"],
                    "scope_id": scope["scope_id"],
                }
            )

        return user

    async def get_user(self, user_id: uuid.UUID) -> Any:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(detail="User not found")
        return user

    async def get_users(
        self,
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        return await self.user_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count_users(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.user_repo.count(filters=filters)

    async def update_user(self, user_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(detail="User not found")
        return await self.user_repo.update(user_id, data)

    async def change_password(
        self, user_id: uuid.UUID, current_password: str, new_password: str
    ) -> Any:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(detail="User not found")
        if not verify_password(current_password, user.password_hash):
            raise BadRequestException(detail="Current password is incorrect")
        return await self.user_repo.update(
            user_id, {"password_hash": hash_password(new_password)}
        )

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(detail="User not found")
        return await self.user_repo.delete(user_id)
