import uuid
from datetime import datetime
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, verify_location_in_scope
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.slot_event import SlotEventRepository
from src.app.schemas.slot_event import ParkingSessionResponse, SlotEventResponse
from src.app.schemas.base import PaginatedResponse
from src.app.services.slot_event import SlotEventService
from src.app.utils.pagination import get_pagination_params, build_paginated_response

router = APIRouter(prefix="/slot-events", tags=["Slot Events"])


def get_service(db: AsyncSession = Depends(get_db)) -> SlotEventService:
    return SlotEventService(SlotEventRepository(db), db)


@router.get("/history", response_model=PaginatedResponse[ParkingSessionResponse])
async def get_parking_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    area_id: uuid.UUID = Query(None),
    location_id: uuid.UUID = Query(None),
    camera_id: uuid.UUID = Query(None),
    slot_id: uuid.UUID = Query(None),
    status: Optional[str] = Query(None, description="Filter by status: parked or completed"),
    event_type: Optional[str] = Query(None, description="Filter by event type: VEHICLE or OBSTRUCTED"),
    min_duration: Optional[float] = Query(None, description="Minimum duration in minutes"),
    max_duration: Optional[float] = Query(None, description="Maximum duration in minutes"),
    start_date: Optional[str] = Query(None, description="ISO format: 2026-05-01T00:00:00"),
    end_date: Optional[str] = Query(None, description="ISO format: 2026-05-10T23:59:59"),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_VIEW)),
    location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    service: SlotEventService = Depends(get_service),
):
    """Get parking sessions (vehicle entry → exit with duration)."""
    skip, limit = get_pagination_params(page, page_size)
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None

    items, total = await service.get_parking_sessions(
        location_ids=location_ids,
        area_id=area_id,
        location_id=location_id,
        camera_id=camera_id,
        slot_id=slot_id,
        status=status,
        event_type=event_type,
        min_duration=min_duration,
        max_duration=max_duration,
        start_time=start,
        end_time=end,
        skip=skip,
        limit=limit,
    )
    return build_paginated_response(items, total, page, limit)


@router.get("/{slot_id}", response_model=list[SlotEventResponse])
async def get_slot_events(
    slot_id: uuid.UUID,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    _: bool = Depends(PermissionChecker(Permission.SLOTS_VIEW)),
    location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    service: SlotEventService = Depends(get_service),
    db: AsyncSession = Depends(get_db),
):
    """Get raw state change events for a slot."""
    # Resolve slot → zone → floor → location_id for scope check
    from src.app.repositories.parking_slot import ParkingSlotRepository
    from src.app.repositories.zone import ZoneRepository
    from src.app.repositories.floor import FloorRepository
    slot = await ParkingSlotRepository(db).get_by_id(slot_id)
    if slot:
        zone = await ZoneRepository(db).get_by_id(slot.zone_id)
        if zone:
            floor = await FloorRepository(db).get_by_id(zone.floor_id)
            if floor:
                verify_location_in_scope(floor.location_id, location_ids)

    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None
    return await service.get_events_by_slot(slot_id, start, end, limit)
