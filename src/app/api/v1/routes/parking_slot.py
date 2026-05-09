import uuid
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids
from src.app.core.constants import Permission, SlotState
from src.app.db.session import get_db
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.repositories.slot_event import SlotEventRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.parking_slot import (
    ParkingSlotCreate,
    ParkingSlotResponse,
    ParkingSlotUpdate,
)
from src.app.services.parking_slot import ParkingSlotService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/parking-slots", tags=["Parking Slots"])


def get_slot_service(db: AsyncSession = Depends(get_db)) -> ParkingSlotService:
    return ParkingSlotService(
        slot_repo=ParkingSlotRepository(db),
        event_repo=SlotEventRepository(db),
    )


@router.post(
    "",
    response_model=ParkingSlotResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.LOCATIONS_MANAGE))],
)
async def create_slot(
    body: ParkingSlotCreate,
    service: ParkingSlotService = Depends(get_slot_service),
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[ParkingSlotResponse])
async def list_slots(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    zone_id: uuid.UUID = Query(None),
    state: SlotState = Query(None),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_VIEW)),
    location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if zone_id:
        filters["zone_id"] = zone_id
    if state:
        filters["state"] = state
    repo = ParkingSlotRepository(db)
    items = await repo.get_scoped(location_ids, skip=skip, limit=limit, filters=filters or None)
    total = await repo.count_scoped(location_ids, filters=filters or None)
    return build_paginated_response(items, total, page, limit)


@router.get("/{slot_id}", response_model=ParkingSlotResponse)
async def get_slot(
    slot_id: uuid.UUID,
    service: ParkingSlotService = Depends(get_slot_service),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_VIEW)),
):
    return await service.get(slot_id)


@router.get("/zone/{zone_id}/stats")
async def get_zone_occupancy(
    zone_id: uuid.UUID,
    service: ParkingSlotService = Depends(get_slot_service),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_VIEW)),
):
    return await service.get_occupancy_stats(zone_id)


@router.patch("/{slot_id}", response_model=ParkingSlotResponse)
async def update_slot(
    slot_id: uuid.UUID,
    body: ParkingSlotUpdate,
    service: ParkingSlotService = Depends(get_slot_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    return await service.update(slot_id, body.model_dump(exclude_unset=True))


@router.delete("/{slot_id}", response_model=MessageResponse)
async def delete_slot(
    slot_id: uuid.UUID,
    service: ParkingSlotService = Depends(get_slot_service),
    _: bool = Depends(PermissionChecker(Permission.LOCATIONS_MANAGE)),
):
    await service.delete(slot_id)
    return MessageResponse(message="Parking slot deleted successfully")
