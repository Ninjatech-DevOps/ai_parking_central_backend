import uuid
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, verify_location_in_scope
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
from src.app.services.device_config_push import push_slots_config
from src.app.repositories.camera import CameraRepository
from src.app.repositories.device import DeviceRepository
from src.app.utils.pagination import build_paginated_response, get_pagination_params

from src.app.repositories.zone import ZoneRepository
from src.app.repositories.floor import FloorRepository

router = APIRouter(prefix="/parking-slots", tags=["Parking Slots"])


async def _verify_slot_scope(
    slot_id: uuid.UUID,
    user_location_ids: Optional[Set[uuid.UUID]],
    db: AsyncSession,
) -> None:
    """Resolve slot → zone → floor → location_id, then check scope."""
    slot = await ParkingSlotRepository(db).get_by_id(slot_id)
    if not slot:
        return
    zone = await ZoneRepository(db).get_by_id(slot.zone_id)
    if not zone:
        return
    floor = await FloorRepository(db).get_by_id(zone.floor_id)
    if floor:
        verify_location_in_scope(floor.location_id, user_location_ids)


async def _verify_zone_scope(
    zone_id: uuid.UUID,
    user_location_ids: Optional[Set[uuid.UUID]],
    db: AsyncSession,
) -> None:
    """Resolve zone → floor → location_id, then check scope."""
    zone = await ZoneRepository(db).get_by_id(zone_id)
    if not zone:
        return
    floor = await FloorRepository(db).get_by_id(zone.floor_id)
    if floor:
        verify_location_in_scope(floor.location_id, user_location_ids)


def get_slot_service(db: AsyncSession = Depends(get_db)) -> ParkingSlotService:
    return ParkingSlotService(
        slot_repo=ParkingSlotRepository(db),
        event_repo=SlotEventRepository(db),
    )


@router.post(
    "",
    response_model=ParkingSlotResponse,
    status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.SLOTS_CREATE))],
)
async def create_slot(
    body: ParkingSlotCreate,
    service: ParkingSlotService = Depends(get_slot_service),
    db: AsyncSession = Depends(get_db),
):
    slot = await service.create(body.model_dump())
    await _push_camera_slots(db, slot.camera_id)
    return slot


@router.get("", response_model=PaginatedResponse[ParkingSlotResponse])
async def list_slots(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    zone_id: uuid.UUID = Query(None),
    camera_id: uuid.UUID = Query(None),
    state: SlotState = Query(None),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_VIEW)),
    location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if zone_id:
        filters["zone_id"] = zone_id
    if camera_id:
        filters["camera_id"] = camera_id
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
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_slot_scope(slot_id, user_location_ids, db)
    return await service.get(slot_id)


@router.get("/zone/{zone_id}/stats")
async def get_zone_occupancy(
    zone_id: uuid.UUID,
    service: ParkingSlotService = Depends(get_slot_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_zone_scope(zone_id, user_location_ids, db)
    return await service.get_occupancy_stats(zone_id)


@router.patch("/{slot_id}", response_model=ParkingSlotResponse)
async def update_slot(
    slot_id: uuid.UUID,
    body: ParkingSlotUpdate,
    service: ParkingSlotService = Depends(get_slot_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_EDIT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_slot_scope(slot_id, user_location_ids, db)
    slot = await service.update(slot_id, body.model_dump(exclude_unset=True))
    await _push_camera_slots(db, slot.camera_id)
    return slot


@router.delete("/{slot_id}", response_model=MessageResponse)
async def delete_slot(
    slot_id: uuid.UUID,
    service: ParkingSlotService = Depends(get_slot_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_DELETE)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_slot_scope(slot_id, user_location_ids, db)
    slot = await service.get(slot_id)
    camera_id = slot.camera_id
    await service.delete(slot_id)
    await db.flush()  # ensure soft-delete is visible before querying active slots
    await _push_camera_slots(db, camera_id)
    return MessageResponse(message="Parking slot deleted successfully")


async def _push_camera_slots(db: AsyncSession, camera_id) -> None:
    """Push all slots for a camera to the edge device via MQTT."""
    if not camera_id:
        return
    cam_repo = CameraRepository(db)
    camera = await cam_repo.get_by_id(camera_id)
    if not camera:
        return
    device = await DeviceRepository(db).get_by_id(camera.device_id)
    if not device:
        return

    slot_repo = ParkingSlotRepository(db)
    slots = await slot_repo.get_by_camera_id(camera.id)
    push_slots_config(device.device_id, camera.position_label, [
        {
            "label": s.label,
            "slot_type": s.slot_type or "GENERAL",
            "polygon_coords": s.polygon_coords,
            "pos_x1": s.pos_x1, "pos_y1": s.pos_y1,
            "pos_x2": s.pos_x2, "pos_y2": s.pos_y2,
        }
        for s in slots
    ])
