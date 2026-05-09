import uuid
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.location import LocationRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.location import LocationCreate, LocationResponse, LocationUpdate
from src.app.services.location import LocationService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/locations", tags=["Locations"])


def get_location_service(db: AsyncSession = Depends(get_db)) -> LocationService:
    return LocationService(location_repo=LocationRepository(db))


@router.post(
    "",
    response_model=LocationResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_MANAGE))],
)
async def create_location(
    body: LocationCreate, service: LocationService = Depends(get_location_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[LocationResponse])
async def list_locations(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    area_id: uuid.UUID = Query(None),
    service: LocationService = Depends(get_location_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
    location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {"area_id": area_id} if area_id else None
    repo = LocationRepository(db)
    items = await repo.get_scoped(location_ids, skip=skip, limit=limit, filters=filters)
    total = await repo.count_scoped(location_ids, filters=filters)
    return build_paginated_response(items, total, page, limit)


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: uuid.UUID,
    service: LocationService = Depends(get_location_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    return await service.get(location_id)


@router.patch("/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: uuid.UUID,
    body: LocationUpdate,
    service: LocationService = Depends(get_location_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    return await service.update(location_id, body.model_dump(exclude_unset=True))


@router.delete("/{location_id}", response_model=MessageResponse)
async def delete_location(
    location_id: uuid.UUID,
    service: LocationService = Depends(get_location_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    await service.delete(location_id)
    return MessageResponse(message="Location deleted successfully")
