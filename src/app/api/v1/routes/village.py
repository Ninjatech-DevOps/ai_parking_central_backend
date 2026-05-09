import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.village import VillageRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.village import VillageCreate, VillageResponse, VillageUpdate
from src.app.services.village import VillageService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/villages", tags=["Villages"])


def get_village_service(db: AsyncSession = Depends(get_db)) -> VillageService:
    return VillageService(village_repo=VillageRepository(db))


@router.post(
    "",
    response_model=VillageResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_MANAGE))],
)
async def create_village(
    body: VillageCreate, service: VillageService = Depends(get_village_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[VillageResponse])
async def list_villages(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    taluka_id: uuid.UUID = Query(None),
    service: VillageService = Depends(get_village_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {"taluka_id": taluka_id} if taluka_id else None
    items = await service.get_all(skip=skip, limit=limit, filters=filters)
    total = await service.count(filters=filters)
    return build_paginated_response(items, total, page, limit)


@router.get("/{village_id}", response_model=VillageResponse)
async def get_village(
    village_id: uuid.UUID,
    service: VillageService = Depends(get_village_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    return await service.get(village_id)


@router.patch("/{village_id}", response_model=VillageResponse)
async def update_village(
    village_id: uuid.UUID,
    body: VillageUpdate,
    service: VillageService = Depends(get_village_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    return await service.update(village_id, body.model_dump(exclude_unset=True))


@router.delete("/{village_id}", response_model=MessageResponse)
async def delete_village(
    village_id: uuid.UUID,
    service: VillageService = Depends(get_village_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    await service.delete(village_id)
    return MessageResponse(message="Village deleted successfully")
