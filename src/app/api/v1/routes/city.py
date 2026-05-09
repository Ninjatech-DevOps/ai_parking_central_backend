import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.city import CityRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.city import CityCreate, CityResponse, CityUpdate
from src.app.services.city import CityService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/cities", tags=["Cities"])


def get_city_service(db: AsyncSession = Depends(get_db)) -> CityService:
    return CityService(city_repo=CityRepository(db))


@router.post(
    "",
    response_model=CityResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_MANAGE))],
)
async def create_city(
    body: CityCreate, service: CityService = Depends(get_city_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[CityResponse])
async def list_cities(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    state_id: uuid.UUID = Query(None),
    service: CityService = Depends(get_city_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {"state_id": state_id} if state_id else None
    items = await service.get_all(skip=skip, limit=limit, filters=filters)
    total = await service.count(filters=filters)
    return build_paginated_response(items, total, page, limit)


@router.get("/{city_id}", response_model=CityResponse)
async def get_city(
    city_id: uuid.UUID,
    service: CityService = Depends(get_city_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    return await service.get(city_id)


@router.patch("/{city_id}", response_model=CityResponse)
async def update_city(
    city_id: uuid.UUID,
    body: CityUpdate,
    service: CityService = Depends(get_city_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    return await service.update(city_id, body.model_dump(exclude_unset=True))


@router.delete("/{city_id}", response_model=MessageResponse)
async def delete_city(
    city_id: uuid.UUID,
    service: CityService = Depends(get_city_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    await service.delete(city_id)
    return MessageResponse(message="City deleted successfully")
