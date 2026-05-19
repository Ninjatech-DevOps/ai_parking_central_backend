import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.state import StateRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.state import StateCreate, StateResponse, StateUpdate
from src.app.services.state import StateService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/states", tags=["States"])


def get_state_service(db: AsyncSession = Depends(get_db)) -> StateService:
    return StateService(state_repo=StateRepository(db))


@router.post(
    "",
    response_model=StateResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_CREATE))],
)
async def create_state(
    body: StateCreate, service: StateService = Depends(get_state_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[StateResponse])
async def list_states(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    service: StateService = Depends(get_state_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    items = await service.get_all(skip=skip, limit=limit)
    total = await service.count()
    return build_paginated_response(items, total, page, limit)


@router.get("/{state_id}", response_model=StateResponse)
async def get_state(
    state_id: uuid.UUID,
    service: StateService = Depends(get_state_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_VIEW)),
):
    return await service.get(state_id)


@router.patch("/{state_id}", response_model=StateResponse)
async def update_state(
    state_id: uuid.UUID,
    body: StateUpdate,
    service: StateService = Depends(get_state_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_EDIT)),
):
    return await service.update(state_id, body.model_dump(exclude_unset=True))


@router.delete("/{state_id}", response_model=MessageResponse)
async def delete_state(
    state_id: uuid.UUID,
    service: StateService = Depends(get_state_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_DELETE)),
):
    await service.delete(state_id)
    return MessageResponse(message="State deleted successfully")
