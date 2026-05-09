import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.taluka import TalukaRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.taluka import TalukaCreate, TalukaResponse, TalukaUpdate
from src.app.services.taluka import TalukaService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/talukas", tags=["Talukas"])


def get_taluka_service(db: AsyncSession = Depends(get_db)) -> TalukaService:
    return TalukaService(taluka_repo=TalukaRepository(db))


@router.post(
    "",
    response_model=TalukaResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_MANAGE))],
)
async def create_taluka(
    body: TalukaCreate, service: TalukaService = Depends(get_taluka_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[TalukaResponse])
async def list_talukas(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    city_id: uuid.UUID = Query(None),
    service: TalukaService = Depends(get_taluka_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {"city_id": city_id} if city_id else None
    items = await service.get_all(skip=skip, limit=limit, filters=filters)
    total = await service.count(filters=filters)
    return build_paginated_response(items, total, page, limit)


@router.get("/{taluka_id}", response_model=TalukaResponse)
async def get_taluka(
    taluka_id: uuid.UUID,
    service: TalukaService = Depends(get_taluka_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    return await service.get(taluka_id)


@router.patch("/{taluka_id}", response_model=TalukaResponse)
async def update_taluka(
    taluka_id: uuid.UUID,
    body: TalukaUpdate,
    service: TalukaService = Depends(get_taluka_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    return await service.update(taluka_id, body.model_dump(exclude_unset=True))


@router.delete("/{taluka_id}", response_model=MessageResponse)
async def delete_taluka(
    taluka_id: uuid.UUID,
    service: TalukaService = Depends(get_taluka_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    await service.delete(taluka_id)
    return MessageResponse(message="Taluka deleted successfully")
