import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.area import AreaRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.area import AreaCreate, AreaResponse, AreaUpdate
from src.app.services.area import AreaService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/areas", tags=["Areas"])


def get_area_service(db: AsyncSession = Depends(get_db)) -> AreaService:
    return AreaService(area_repo=AreaRepository(db))


@router.post("", response_model=AreaResponse, status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_MANAGE))])
async def create_area(
    body: AreaCreate, service: AreaService = Depends(get_area_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[AreaResponse])
async def list_areas(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    city_id: uuid.UUID = Query(None),
    taluka_id: uuid.UUID = Query(None),
    village_id: uuid.UUID = Query(None),
    service: AreaService = Depends(get_area_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if city_id: filters["city_id"] = city_id
    if taluka_id: filters["taluka_id"] = taluka_id
    if village_id: filters["village_id"] = village_id
    items = await service.get_all(skip=skip, limit=limit, filters=filters or None)
    total = await service.count(filters=filters or None)
    return build_paginated_response(items, total, page, limit)


@router.get("/{area_id}", response_model=AreaResponse)
async def get_area(
    area_id: uuid.UUID,
    service: AreaService = Depends(get_area_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    return await service.get(area_id)


@router.patch("/{area_id}", response_model=AreaResponse)
async def update_area(
    area_id: uuid.UUID,
    body: AreaUpdate,
    service: AreaService = Depends(get_area_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    return await service.update(area_id, body.model_dump(exclude_unset=True))


@router.delete("/{area_id}", response_model=MessageResponse)
async def delete_area(
    area_id: uuid.UUID,
    service: AreaService = Depends(get_area_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    await service.delete(area_id)
    return MessageResponse(message="Area deleted successfully")
