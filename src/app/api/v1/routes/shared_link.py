import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_current_user
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.repositories.camera import CameraRepository
from src.app.repositories.device import DeviceRepository
from src.app.repositories.location import LocationRepository
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.repositories.shared_link import SharedLinkRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.shared_link import SharedLinkCreate, SharedLinkResponse, SharedLinkUpdate
from src.app.services.shared_link import SharedLinkService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/shared-links", tags=["Shared Links"])


def get_shared_link_service(db: AsyncSession = Depends(get_db)) -> SharedLinkService:
    return SharedLinkService(
        shared_link_repo=SharedLinkRepository(db),
        location_repo=LocationRepository(db),
        device_repo=DeviceRepository(db),
        camera_repo=CameraRepository(db),
        slot_repo=ParkingSlotRepository(db),
    )


@router.post(
    "",
    response_model=SharedLinkResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.SHARED_LINKS_CREATE))],
)
async def create_shared_link(
    body: SharedLinkCreate,
    service: SharedLinkService = Depends(get_shared_link_service),
    current_user: User = Depends(get_current_user),
):
    return await service.create(body.model_dump(), current_user.id)


@router.get(
    "",
    response_model=PaginatedResponse[SharedLinkResponse],
    dependencies=[Depends(PermissionChecker(Permission.SHARED_LINKS_VIEW))],
)
async def list_shared_links(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    search: str = Query(None),
    is_active: bool = Query(None),
    scope_type: str = Query(None),
    service: SharedLinkService = Depends(get_shared_link_service),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if is_active is not None:
        filters["is_active"] = is_active
    if scope_type:
        filters["scope_type"] = scope_type
    items = await service.get_all(skip=skip, limit=limit, search=search, filters=filters or None)
    total = await service.count(search=search, filters=filters or None)
    return build_paginated_response(items, total, page, limit)


@router.get(
    "/{link_id}",
    response_model=SharedLinkResponse,
    dependencies=[Depends(PermissionChecker(Permission.SHARED_LINKS_VIEW))],
)
async def get_shared_link(
    link_id: uuid.UUID,
    service: SharedLinkService = Depends(get_shared_link_service),
):
    return await service.get(link_id)


@router.patch(
    "/{link_id}",
    response_model=SharedLinkResponse,
    dependencies=[Depends(PermissionChecker(Permission.SHARED_LINKS_EDIT))],
)
async def update_shared_link(
    link_id: uuid.UUID,
    body: SharedLinkUpdate,
    service: SharedLinkService = Depends(get_shared_link_service),
):
    return await service.update(link_id, body.model_dump(exclude_unset=True))


@router.delete(
    "/{link_id}",
    response_model=MessageResponse,
    dependencies=[Depends(PermissionChecker(Permission.SHARED_LINKS_DELETE))],
)
async def delete_shared_link(
    link_id: uuid.UUID,
    service: SharedLinkService = Depends(get_shared_link_service),
):
    await service.delete(link_id)
    return MessageResponse(message="Shared link deleted successfully")
