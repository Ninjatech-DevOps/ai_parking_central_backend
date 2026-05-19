import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.role import RoleRepository
from src.app.repositories.role_permission import RolePermissionRepository
from src.app.repositories.permission import PermissionRepository
from src.app.repositories.user_role import UserRoleRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.role import RoleCreate, RoleResponse, RoleUpdate
from src.app.schemas.permission import PermissionResponse
from src.app.services.role import RoleService

router = APIRouter(prefix="/roles", tags=["Roles"])


def get_role_service(db: AsyncSession = Depends(get_db)) -> RoleService:
    return RoleService(
        role_repo=RoleRepository(db),
        role_perm_repo=RolePermissionRepository(db),
        permission_repo=PermissionRepository(db),
        user_role_repo=UserRoleRepository(db),
    )


@router.get("", response_model=PaginatedResponse[RoleResponse])
async def list_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    service: RoleService = Depends(get_role_service),
    _: bool = Depends(PermissionChecker(Permission.USERS_VIEW)),
):
    """List all roles with their permissions and user counts."""
    skip = (page - 1) * page_size
    items = await service.get_roles(skip=skip, limit=page_size)
    total = await service.count_roles()
    total_pages = (total + page_size - 1) // page_size
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    service: RoleService = Depends(get_role_service),
    _: bool = Depends(PermissionChecker(Permission.USERS_VIEW)),
):
    """List all available permissions in the system."""
    return await service.get_all_permissions()


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: uuid.UUID,
    service: RoleService = Depends(get_role_service),
    _: bool = Depends(PermissionChecker(Permission.USERS_VIEW)),
):
    return await service.get_role(role_id)


@router.post("", response_model=RoleResponse, status_code=201)
async def create_role(
    body: RoleCreate,
    service: RoleService = Depends(get_role_service),
    _: bool = Depends(PermissionChecker(Permission.ROLES_CREATE)),
):
    """Create a custom role with optional permission assignments."""
    return await service.create_role(body.model_dump())


@router.patch("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    service: RoleService = Depends(get_role_service),
    _: bool = Depends(PermissionChecker(Permission.ROLES_EDIT)),
):
    """Update a custom role. System roles cannot be modified."""
    return await service.update_role(role_id, body.model_dump(exclude_unset=True))


@router.delete("/{role_id}", response_model=MessageResponse)
async def delete_role(
    role_id: uuid.UUID,
    service: RoleService = Depends(get_role_service),
    _: bool = Depends(PermissionChecker(Permission.ROLES_DELETE)),
):
    """Delete a custom role. System roles and roles with assigned users cannot be deleted."""
    await service.delete_role(role_id)
    return MessageResponse(message="Role deleted successfully")
