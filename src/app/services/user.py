import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import ScopeType
from src.app.core.security import hash_password, verify_password
from src.app.exceptions.base import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from src.app.models.state import State
from src.app.models.city import City
from src.app.models.area import Area
from src.app.models.location import Location
from src.app.models.zone import Zone
from src.app.repositories.user import UserRepository
from src.app.repositories.user_role import UserRoleRepository
from src.app.repositories.user_scope import UserScopeRepository
from src.app.repositories.role_permission import RolePermissionRepository


_SCOPE_MODEL_MAP = {
    ScopeType.STATE: State,
    ScopeType.CITY: City,
    ScopeType.AREA: Area,
    ScopeType.LOCATION: Location,
    ScopeType.ZONE: Zone,
}


class UserService:
    def __init__(
        self,
        user_repo: UserRepository,
        user_role_repo: UserRoleRepository,
        user_scope_repo: UserScopeRepository,
        role_perm_repo: RolePermissionRepository,
        db: AsyncSession = None,
    ):
        self.user_repo = user_repo
        self.user_role_repo = user_role_repo
        self.user_scope_repo = user_scope_repo
        self.role_perm_repo = role_perm_repo
        self.db = db

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

        # Re-fetch to load relationships (user_roles, user_scopes are selectin)
        return await self.user_repo.get_by_id(user.id)

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

        # Handle role_ids: replace all user roles
        role_ids = data.pop("role_ids", None)
        if role_ids is not None:
            await self.user_role_repo.delete_by_user_id(user_id)
            for role_id in role_ids:
                await self.user_role_repo.create(
                    {"user_id": user_id, "role_id": role_id}
                )

        # Handle scopes: replace all user scopes
        scopes = data.pop("scopes", None)
        if scopes is not None:
            await self.user_scope_repo.delete_by_user_id(user_id)
            for scope in scopes:
                await self.user_scope_repo.create(
                    {
                        "user_id": user_id,
                        "scope_type": scope["scope_type"],
                        "scope_id": scope["scope_id"],
                    }
                )

        # Update remaining user fields (name, phone, is_active, etc.)
        if data:
            await self.user_repo.update(user_id, data)

        # Re-fetch to load updated relationships
        return await self.user_repo.get_by_id(user_id)

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

    async def delete_user(self, user_id: uuid.UUID):
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(detail="User not found")
        return await self.user_repo.update(user_id, {"is_active": False})

    async def get_user_permissions(self, user_id: uuid.UUID) -> List[str]:
        """Resolve all permission keys for a user via their roles."""
        user_roles = await self.user_role_repo.get_by_user_id(user_id)
        permissions = set()
        for ur in user_roles:
            role_perms = await self.role_perm_repo.get_by_role_id(ur.role_id)
            for rp in role_perms:
                permissions.add(rp.permission.key)
        return sorted(permissions)

    async def _resolve_scope_name(self, scope_type: str, scope_id: uuid.UUID) -> Optional[str]:
        """Look up the name for a scope entity."""
        if not self.db:
            return None
        model = _SCOPE_MODEL_MAP.get(scope_type)
        if not model:
            return None
        result = await self.db.execute(
            select(model.name).where(model.id == scope_id)
        )
        row = result.scalar_one_or_none()
        return row if row else None

    async def build_user_response(self, user: Any) -> Dict[str, Any]:
        """Build user dict with roles and scopes from loaded relationships."""
        roles = []
        for ur in (user.user_roles or []):
            if ur.role:
                roles.append({
                    "id": ur.role.id,
                    "name": ur.role.name,
                    "description": ur.role.description,
                })

        scopes = []
        for us in (user.user_scopes or []):
            scope_name = await self._resolve_scope_name(us.scope_type, us.scope_id)
            scopes.append({
                "id": us.id,
                "scope_type": us.scope_type,
                "scope_id": us.scope_id,
                "scope_name": scope_name,
            })

        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "phone": user.phone,
            "is_active": user.is_active,
            "fcm_tokens": user.fcm_tokens,
            "roles": roles,
            "scopes": scopes,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    async def build_me_response(self, user: Any) -> Dict[str, Any]:
        """Build enriched /users/me response with permissions list."""
        base = await self.build_user_response(user)
        base.pop("fcm_tokens", None)
        base["permissions"] = await self.get_user_permissions(user.id)
        return base
