import uuid
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_current_user, get_user_location_ids
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.repositories.user import UserRepository
from src.app.repositories.user_role import UserRoleRepository
from src.app.repositories.user_scope import UserScopeRepository
from src.app.repositories.role_permission import RolePermissionRepository
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import update as sa_update

from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.user import (
    ChangePassword,
    UserCreate,
    UserMeResponse,
    UserResponse,
    UserUpdate,
)
from src.app.services.user import UserService
from src.app.utils.pagination import build_paginated_response, get_pagination_params


class FcmTokenBody(PydanticBaseModel):
    token: str

router = APIRouter(prefix="/users", tags=["Users"])


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(
        user_repo=UserRepository(db),
        user_role_repo=UserRoleRepository(db),
        user_scope_repo=UserScopeRepository(db),
        role_perm_repo=RolePermissionRepository(db),
        db=db,
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.USERS_CREATE))],
)
async def create_user(
    body: UserCreate, service: UserService = Depends(get_user_service)
):
    user = await service.create_user(body.model_dump())
    return await service.build_user_response(user)


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.USERS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {"is_active": True}

    # Resolve which users are visible to the current user
    visible_user_ids = None  # None = super admin, sees all
    if user_location_ids is not None:
        # Scoped user — only show users whose ENTIRE access fits within my scope.
        # A location manager should NOT see city managers or super admins.
        from src.app.services.scope_resolver import ScopeResolver
        from src.app.models.user_scope import UserScope
        from src.app.models.user import User as UserModel
        from sqlalchemy import select as sa_select

        resolver = ScopeResolver(db)
        my_locs = user_location_ids

        # Get all active users (except self)
        result = await db.execute(
            sa_select(UserModel.id).where(UserModel.is_active == True)
        )
        all_user_ids = [row[0] for row in result.all()]

        visible_ids: set = set()
        for uid in all_user_ids:
            # Skip super admins — they have no scopes, their access is unlimited
            if await resolver.is_super_admin(uid):
                continue
            # Resolve this user's location access
            their_locs = await resolver.resolve_location_ids(uid)
            if their_locs is None:
                continue  # Super admin (shouldn't reach here but safety check)
            if len(their_locs) == 0:
                continue  # No scopes assigned — invisible
            # Show only if their entire access is within my scope
            if their_locs.issubset(my_locs):
                visible_ids.add(uid)

        visible_user_ids = visible_ids

    repo = UserRepository(db)
    users = await repo.get_scoped(visible_user_ids, skip=skip, limit=limit, filters=filters)
    total = await repo.count_scoped(visible_user_ids, filters=filters)
    items = [await service.build_user_response(u) for u in users]
    return build_paginated_response(items, total, page, limit)


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Returns current user with roles, permissions, and scopes."""
    return await service.build_me_response(current_user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
    _: bool = Depends(PermissionChecker(Permission.USERS_VIEW)),
):
    user = await service.get_user(user_id)
    return await service.build_user_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    service: UserService = Depends(get_user_service),
    _: bool = Depends(PermissionChecker(Permission.USERS_EDIT)),
):
    user = await service.update_user(user_id, body.model_dump(exclude_unset=True))
    return await service.build_user_response(user)


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePassword,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    await service.change_password(
        current_user.id, body.current_password, body.new_password
    )
    return MessageResponse(message="Password changed successfully")


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
    _: bool = Depends(PermissionChecker(Permission.USERS_DELETE)),
):
    await service.delete_user(user_id)
    return MessageResponse(message="User deleted successfully")


@router.post("/me/fcm-token", response_model=MessageResponse)
async def register_fcm_token(
    body: FcmTokenBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register an FCM token for push notifications.
    Removes the token from any other user first (one browser = one user).
    """
    from sqlalchemy import select as sa_select
    # Remove this token from ALL other users (browser switched accounts)
    result = await db.execute(sa_select(User).where(User.id != current_user.id))
    for other_user in result.scalars().all():
        other_tokens = list(other_user.fcm_tokens or [])
        if body.token in other_tokens:
            other_tokens.remove(body.token)
            await db.execute(
                sa_update(User).where(User.id == other_user.id).values(fcm_tokens=other_tokens)
            )

    # Add to current user
    tokens = list(current_user.fcm_tokens or [])
    if body.token not in tokens:
        tokens.append(body.token)
        await db.execute(
            sa_update(User).where(User.id == current_user.id).values(fcm_tokens=tokens)
        )
    await db.commit()
    return MessageResponse(message="FCM token registered")


@router.delete("/me/fcm-token", response_model=MessageResponse)
async def remove_fcm_token(
    body: FcmTokenBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an FCM token (e.g. on logout)."""
    tokens = list(current_user.fcm_tokens or [])
    if body.token in tokens:
        tokens.remove(body.token)
        await db.execute(
            sa_update(User).where(User.id == current_user.id).values(fcm_tokens=tokens)
        )
        await db.commit()
    return MessageResponse(message="FCM token removed")
