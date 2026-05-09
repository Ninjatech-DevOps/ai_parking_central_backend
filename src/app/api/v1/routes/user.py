import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_current_user
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.repositories.user import UserRepository
from src.app.repositories.user_role import UserRoleRepository
from src.app.repositories.user_scope import UserScopeRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.user import (
    ChangePassword,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from src.app.services.user import UserService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/users", tags=["Users"])


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(
        user_repo=UserRepository(db),
        user_role_repo=UserRoleRepository(db),
        user_scope_repo=UserScopeRepository(db),
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
    return await service.create_user(body.model_dump())


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    service: UserService = Depends(get_user_service),
    _: bool = Depends(PermissionChecker(Permission.USERS_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    users = await service.get_users(skip=skip, limit=limit)
    total = await service.count_users()
    return build_paginated_response(users, total, page, limit)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
    _: bool = Depends(PermissionChecker(Permission.USERS_VIEW)),
):
    return await service.get_user(user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    service: UserService = Depends(get_user_service),
    _: bool = Depends(PermissionChecker(Permission.USERS_EDIT)),
):
    return await service.update_user(user_id, body.model_dump(exclude_unset=True))


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
