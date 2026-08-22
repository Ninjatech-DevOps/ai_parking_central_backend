"""Vehicle counter totals for the central system.

Separate from ``src.app.vehicle_counter.routes`` on purpose. That module is
guarded by a single shared password and serves the operator's tablet; this
endpoint is consumed by the central system and is guarded by a normal user JWT
plus a role permission.

The data itself is the same: this reads the counter's standalone SQLite
database through the counter's own service, so the aggregation rules -- soft
deletes excluded, counts derived from ``direction`` -- are shared rather than
reimplemented here.

Both databases are injected into the one request: Postgres (via the permission
dependency) authenticates the caller, SQLite holds the events.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.schemas.base import PaginatedResponse
from src.app.utils.pagination import build_paginated_response, get_pagination_params
from src.app.vehicle_counter.datetime_utils import parse_bound, today_bounds
from src.app.vehicle_counter.db import get_vc_db
from src.app.vehicle_counter.repository import VehicleEventRepository
from src.app.vehicle_counter.schemas import VehicleCounterStats, VehicleEventResponse
from src.app.vehicle_counter.service import VehicleEventService

router = APIRouter(prefix="/vehicle-counter", tags=["Vehicle Counter Report"])


def _resolve_range(start_date: Optional[str], end_date: Optional[str]):
    """Turn the two IST query params into naive-UTC bounds.

    With neither supplied the range is the current IST day. Supplying just one
    leaves the other open-ended -- defaulting its partner would silently
    contradict an explicitly open-ended request.
    """
    start = parse_bound(start_date, end_of_day=False)
    end = parse_bound(end_date, end_of_day=True)
    if start is None and end is None:
        start, end = today_bounds()
    return start, end


@router.get("/stats", response_model=VehicleCounterStats)
async def get_vehicle_counter_stats(
    start_date: Optional[str] = Query(
        None,
        description=(
            "IST date or datetime, e.g. 2026-08-01 or 2026-08-01T09:30. "
            "Defaults, with end_date, to the current IST day."
        ),
    ),
    end_date: Optional[str] = Query(
        None, description="IST date or datetime. A bare date covers the whole day."
    ),
    vc_db: AsyncSession = Depends(get_vc_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
) -> VehicleCounterStats:
    """Car and two-wheeler IN/OUT totals over a date range.

    With neither bound supplied the range is the current IST day. Supplying
    just one leaves the other open-ended, so ``start_date`` alone means
    "everything since", which is a useful shape and not worth forbidding.

    ``currently_inside`` is IN minus OUT *within the range*. Over a bounded
    window that is a net change in occupancy rather than a live count, and can
    be negative -- see ``VehicleEventService.stats``.
    """
    start, end = _resolve_range(start_date, end_date)
    service = VehicleEventService(repo=VehicleEventRepository(vc_db))
    return await service.stats(start, end)


@router.get("/logs", response_model=PaginatedResponse[VehicleEventResponse])
async def get_vehicle_counter_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    vehicle_type: Optional[str] = Query(
        None, description="CAR or TWO_WHEELER. Omit or 'ALL' for both."
    ),
    start_date: Optional[str] = Query(
        None,
        description=(
            "IST date or datetime, e.g. 2026-08-01 or 2026-08-01T09:30. "
            "Defaults, with end_date, to the current IST day."
        ),
    ),
    end_date: Optional[str] = Query(
        None, description="IST date or datetime. A bare date covers the whole day."
    ),
    vc_db: AsyncSession = Depends(get_vc_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
):
    """Individual IN/OUT events over a date range, newest first.

    The rows behind ``/stats``: same filters, same default range, one row per
    button press. Soft-deleted events are excluded from both the page and the
    total.
    """
    start, end = _resolve_range(start_date, end_date)
    skip, limit = get_pagination_params(page, page_size)

    service = VehicleEventService(repo=VehicleEventRepository(vc_db))
    items, total = await service.logs(skip, limit, start, end, vehicle_type)
    return build_paginated_response(items, total, page, limit)
