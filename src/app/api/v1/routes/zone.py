import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.zone import ZoneRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.zone import ZoneCreate, ZoneResponse, ZoneUpdate
from src.app.services.zone import ZoneService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/zones", tags=["Zones"])


def get_zone_service(db: AsyncSession = Depends(get_db)) -> ZoneService:
    return ZoneService(zone_repo=ZoneRepository(db))


@router.post(
    "",
    response_model=ZoneResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_CREATE))],
)
async def create_zone(
    body: ZoneCreate, service: ZoneService = Depends(get_zone_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[ZoneResponse])
async def list_zones(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    floor_id: uuid.UUID = Query(None),
    service: ZoneService = Depends(get_zone_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {"floor_id": floor_id} if floor_id else None
    items = await service.get_all(skip=skip, limit=limit, filters=filters)
    total = await service.count(filters=filters)
    return build_paginated_response(items, total, page, limit)


@router.get("/{zone_id}", response_model=ZoneResponse)
async def get_zone(
    zone_id: uuid.UUID,
    service: ZoneService = Depends(get_zone_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    return await service.get(zone_id)


@router.patch("/{zone_id}", response_model=ZoneResponse)
async def update_zone(
    zone_id: uuid.UUID,
    body: ZoneUpdate,
    service: ZoneService = Depends(get_zone_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_EDIT)),
):
    return await service.update(zone_id, body.model_dump(exclude_unset=True))


@router.delete("/{zone_id}", response_model=MessageResponse)
async def delete_zone(
    zone_id: uuid.UUID,
    service: ZoneService = Depends(get_zone_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_DELETE)),
):
    await service.delete(zone_id)
    return MessageResponse(message="Zone deleted successfully")
