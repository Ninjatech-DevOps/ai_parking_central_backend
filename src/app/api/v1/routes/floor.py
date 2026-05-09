import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.floor import FloorRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.floor import FloorCreate, FloorResponse, FloorUpdate
from src.app.services.floor import FloorService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/floors", tags=["Floors"])


def get_floor_service(db: AsyncSession = Depends(get_db)) -> FloorService:
    return FloorService(floor_repo=FloorRepository(db))


@router.post(
    "",
    response_model=FloorResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_MANAGE))],
)
async def create_floor(
    body: FloorCreate, service: FloorService = Depends(get_floor_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[FloorResponse])
async def list_floors(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    location_id: uuid.UUID = Query(None),
    service: FloorService = Depends(get_floor_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {"location_id": location_id} if location_id else None
    items = await service.get_all(skip=skip, limit=limit, filters=filters)
    total = await service.count(filters=filters)
    return build_paginated_response(items, total, page, limit)


@router.get("/{floor_id}", response_model=FloorResponse)
async def get_floor(
    floor_id: uuid.UUID,
    service: FloorService = Depends(get_floor_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    return await service.get(floor_id)


@router.patch("/{floor_id}", response_model=FloorResponse)
async def update_floor(
    floor_id: uuid.UUID,
    body: FloorUpdate,
    service: FloorService = Depends(get_floor_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    return await service.update(floor_id, body.model_dump(exclude_unset=True))


@router.delete("/{floor_id}", response_model=MessageResponse)
async def delete_floor(
    floor_id: uuid.UUID,
    service: FloorService = Depends(get_floor_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    await service.delete(floor_id)
    return MessageResponse(message="Floor deleted successfully")
