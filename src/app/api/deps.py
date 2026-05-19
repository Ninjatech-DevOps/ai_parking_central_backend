import uuid
from typing import List, Optional, Set

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.security import decode_token
from src.app.db.session import get_db
from src.app.exceptions.base import ForbiddenException, UnauthorizedException
from src.app.models.user import User
from src.app.repositories.user import UserRepository
from src.app.repositories.user_role import UserRoleRepository
from src.app.repositories.role_permission import RolePermissionRepository
from src.app.services.scope_resolver import ScopeResolver

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)

    if not payload or payload.get("type") != "access":
        raise UnauthorizedException(detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException(detail="Invalid token payload")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(uuid.UUID(user_id))
    if not user or not user.is_active:
        raise UnauthorizedException(detail="User not found or deactivated")

    return user


async def get_current_user_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[str]:
    user_role_repo = UserRoleRepository(db)
    role_perm_repo = RolePermissionRepository(db)

    user_roles = await user_role_repo.get_by_user_id(current_user.id)
    permissions = set()

    for ur in user_roles:
        role_perms = await role_perm_repo.get_by_role_id(ur.role_id)
        for rp in role_perms:
            permissions.add(rp.permission.key)

    return list(permissions)


async def get_user_location_ids(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[Set[uuid.UUID]]:
    """
    Returns the set of location_ids this user can access.
    Returns None for Super Admin (no filtering — sees everything).
    Returns empty set if user has no scopes (sees nothing).
    """
    resolver = ScopeResolver(db)
    return await resolver.resolve_location_ids(current_user.id)


def verify_location_in_scope(
    location_id: uuid.UUID,
    user_location_ids: Optional[Set[uuid.UUID]],
) -> None:
    """
    Validate that a location_id is within the user's scope.
    None = Super Admin (full access). Empty set = no access.
    """
    if user_location_ids is None:
        return  # Super Admin
    if location_id not in user_location_ids:
        raise ForbiddenException(detail="Access denied — location outside your scope")


class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(
        self,
        permissions: List[str] = Depends(get_current_user_permissions),
    ) -> bool:
        if self.required_permission not in permissions:
            raise ForbiddenException(
                detail=f"Permission '{self.required_permission}' required"
            )
        return True
