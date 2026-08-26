"""Vehicle in/out movements — list, filter and record.

Independent of the ANPR module: these rows come from whatever counts vehicles
at a site, whether or not plate recognition is involved.
"""

import math
import uuid
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import (
    PermissionChecker,
    get_user_location_ids,
    verify_location_in_scope,
)
from src.app.core.constants import MovementDirection, Permission, VehicleType
from src.app.db.session import get_db
from src.app.models.location import Location as LocationModel
from src.app.repositories.vehicle_movement import VehicleMovementRepository
from src.app.schemas.base import MessageResponse
from src.app.schemas.vehicle_movement import (
    VehicleMovementCreate,
    VehicleMovementListResponse,
    VehicleMovementResponse,
    VehicleMovementUpdate,
    build_movement_response,
)
from src.app.services.vehicle_movement import VehicleMovementService
from src.app.utils.pagination import get_pagination_params

router = APIRouter(prefix="/vehicle-movements", tags=["Vehicle Movements"])

# Reports in this system are read in Indian Standard Time, so "today" has to
# mean today in IST regardless of where the browser is. Matches the offset
# already hard-coded in services/parking_analytics.py.
IST = timezone(timedelta(hours=5, minutes=30))


class QuickRange(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"


def _get_service(db: AsyncSession = Depends(get_db)) -> VehicleMovementService:
    return VehicleMovementService(VehicleMovementRepository(db))


def _quick_range_window(choice: QuickRange) -> tuple:
    """Resolve a named range to a UTC [start, end] pair.

    Computed server-side rather than in the browser so every viewer gets the
    same window — a browser in another timezone would otherwise silently ask
    for a different day than the one its dropdown says.
    """
    now_ist = datetime.now(IST)
    today = now_ist.date()

    if choice == QuickRange.TODAY:
        start_date, end_date = today, today
    elif choice == QuickRange.YESTERDAY:
        start_date = end_date = today - timedelta(days=1)
    elif choice == QuickRange.LAST_7_DAYS:
        start_date, end_date = today - timedelta(days=6), today
    elif choice == QuickRange.LAST_30_DAYS:
        start_date, end_date = today - timedelta(days=29), today
    else:  # THIS_MONTH
        start_date, end_date = today.replace(day=1), today

    start = datetime.combine(start_date, time.min, tzinfo=IST)
    # End of the last day, not its midnight — otherwise "today" returns nothing.
    end = datetime.combine(end_date, time.max, tzinfo=IST)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


async def _resolve_scope(area_id, user_location_ids, db):
    if not area_id:
        return user_location_ids
    result = await db.execute(
        select(LocationModel.id).where(LocationModel.area_id == area_id)
    )
    area_loc_ids = {row[0] for row in result.all()}
    return (
        (user_location_ids & area_loc_ids)
        if user_location_ids is not None
        else area_loc_ids
    )


@router.get("", response_model=VehicleMovementListResponse)
async def list_movements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    quick_range: Optional[QuickRange] = Query(
        None,
        description="Named window resolved in IST. Ignored when from_date or "
                    "to_date is supplied.",
    ),
    from_date: Optional[datetime] = Query(None, description="ISO 8601."),
    to_date: Optional[datetime] = Query(None, description="ISO 8601."),
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    camera_id: Optional[uuid.UUID] = Query(
        None,
        description="A camera outside your scope yields no rows rather than "
                    "an error.",
    ),
    vehicle_type: Optional[VehicleType] = Query(None),
    direction: Optional[MovementDirection] = Query(None),
    number_plate: Optional[str] = Query(None),
    service: VehicleMovementService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.VEHICLE_MOVEMENTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    """One page of movements plus In/Out totals for the whole filtered window.

    The totals cover every matching row, not just this page, so the summary
    cards do not change as the user pages through the table.
    """
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped_ids = await _resolve_scope(area_id, user_location_ids, db)

    # An explicit date always beats the dropdown, which is what lets the
    # frontend show "Today" selected and still honour a hand-typed range.
    start, end = from_date, to_date
    if quick_range and start is None and end is None:
        start, end = _quick_range_window(quick_range)

    filters = dict(
        location_id=location_id,
        # Passed through untouched. An empty set means "no locations in scope"
        # and must return nothing; collapsing it to None would drop the filter
        # entirely and expose every location.
        location_ids=scoped_ids,
        camera_id=camera_id,
        vehicle_type=vehicle_type.value if vehicle_type else None,
        direction=direction.value if direction else None,
        number_plate=number_plate,
        start_date=start,
        end_date=end,
    )

    skip, limit = get_pagination_params(page, page_size)
    rows = await service.get_filtered(skip, limit, **filters)
    total = await service.count_filtered(**filters)
    summary = await service.summary(**filters)

    items = [
        build_movement_response(movement, location_name, camera_label)
        for movement, location_name, camera_label in rows
    ]

    return VehicleMovementListResponse(
        items=items,
        total=total,
        page=page,
        page_size=limit,
        total_pages=math.ceil(total / limit) if limit > 0 else 0,
        summary=summary,
    )


@router.post("", response_model=VehicleMovementResponse, status_code=201)
async def create_movement(
    body: VehicleMovementCreate,
    service: VehicleMovementService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.VEHICLE_MOVEMENTS_CREATE)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    verify_location_in_scope(body.location_id, user_location_ids)
    movement = await service.create(body.model_dump())
    # Re-read with labels so the created row carries the same fields the list
    # returns — the frontend can render it without a second request.
    return build_movement_response(*await service.get_with_labels(movement.id))


@router.get("/{movement_id}", response_model=VehicleMovementResponse)
async def get_movement(
    movement_id: uuid.UUID,
    service: VehicleMovementService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.VEHICLE_MOVEMENTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    movement, location_name, camera_label = await service.get_with_labels(movement_id)
    verify_location_in_scope(movement.location_id, user_location_ids)
    return build_movement_response(movement, location_name, camera_label)


@router.patch("/{movement_id}", response_model=VehicleMovementResponse)
async def update_movement(
    movement_id: uuid.UUID,
    body: VehicleMovementUpdate,
    service: VehicleMovementService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.VEHICLE_MOVEMENTS_EDIT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    movement = await service.get(movement_id)
    verify_location_in_scope(movement.location_id, user_location_ids)
    # NOTE: BaseRepository.update drops None values, so an explicit
    # {"number_plate": null} cannot clear the field today. That is a
    # codebase-wide behaviour, not specific to this route.
    await service.update(movement_id, body.model_dump(exclude_unset=True))
    return build_movement_response(*await service.get_with_labels(movement_id))


@router.delete("/{movement_id}", response_model=MessageResponse)
async def delete_movement(
    movement_id: uuid.UUID,
    service: VehicleMovementService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.VEHICLE_MOVEMENTS_DELETE)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    movement = await service.get(movement_id)
    verify_location_in_scope(movement.location_id, user_location_ids)
    await service.delete(movement_id)
    return MessageResponse(message="Vehicle movement deleted successfully")
