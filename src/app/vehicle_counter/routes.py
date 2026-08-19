"""Routes for the vehicle counter module.

Mounted at the top level (``/vehicle-counter``) rather than under ``/api/v1``:
a future blanket auth dependency on ``api_v1_router`` is a plausible one-line
change that would silently break this module, and these routes read a different
database entirely.

NO AUTHENTICATION. The ``?edit`` / ``?delete`` URL params on the records page
are a UI affordance only -- anyone who can reach this port can call PATCH and
DELETE directly. The module is intended for an internal/trusted network.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.utils.export import generate_excel
from src.app.utils.pagination import build_paginated_response, get_pagination_params
from src.app.exceptions.base import BadRequestException
from src.app.vehicle_counter.db import get_vc_db
from src.app.vehicle_counter.repository import VehicleEventRepository
from src.app.vehicle_counter.schemas import (
    CounterPageData,
    VehicleCounterStats,
    VehicleEventCreate,
    VehicleEventResponse,
    VehicleEventUpdate,
)
from src.app.vehicle_counter.service import VehicleEventService

router = APIRouter(prefix="/vehicle-counter", tags=["Vehicle Counter"])

STATIC_DIR = Path(__file__).parent / "static"


def get_vc_service(db: AsyncSession = Depends(get_vc_db)) -> VehicleEventService:
    return VehicleEventService(repo=VehicleEventRepository(db))


# Timestamps are stored in UTC; the UI and the export both present IST so the
# spreadsheet matches what the operator saw on screen.
IST = timezone(timedelta(hours=5, minutes=30))


def _to_ist(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST)


def _parse_bound(value: Optional[str], end_of_day: bool) -> Optional[datetime]:
    """Parse a date or datetime the browser sent, interpreted as IST.

    Accepts 'YYYY-MM-DD' and 'YYYY-MM-DDTHH:MM[:SS]'. A bare date used as the
    upper bound covers the whole day.
    """
    if not value:
        return None
    text = value.strip().replace("Z", "")
    try:
        if len(text) == 10:  # date only
            parsed = datetime.strptime(text, "%Y-%m-%d")
            if end_of_day:
                parsed = parsed.replace(hour=23, minute=59, second=59)
        else:
            parsed = datetime.fromisoformat(text)
    except ValueError:
        raise BadRequestException(detail=f"Invalid date value: {value}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    # Stored timestamps are naive UTC, so compare against naive UTC.
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


# --- Pages ---------------------------------------------------------------


def _page(name: str) -> FileResponse:
    # no-store so an operator's tablet never serves a stale build of the page
    return FileResponse(
        STATIC_DIR / name,
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@router.get("", include_in_schema=False)
async def counter_page_no_slash():
    """Serve the counter page without a 307 redirect."""
    return _page("index.html")


@router.get("/", include_in_schema=False)
async def counter_page():
    return _page("index.html")


@router.get("/records", include_in_schema=False)
async def records_page():
    return _page("records.html")


# --- API -----------------------------------------------------------------


@router.post("/api/events", response_model=VehicleEventResponse, status_code=201)
async def create_event(
    body: VehicleEventCreate,
    service: VehicleEventService = Depends(get_vc_service),
):
    """Record one IN or OUT button press."""
    return await service.record(body.direction, body.timestamp)


@router.get("/api/summary", response_model=CounterPageData)
async def get_summary(
    recent_limit: int = Query(10, ge=1, le=50),
    service: VehicleEventService = Depends(get_vc_service),
):
    """Stats plus the most recent events -- the counter page payload."""
    return CounterPageData(
        stats=await service.stats(),
        recent=await service.repo.recent(recent_limit),
    )


@router.get("/api/stats", response_model=VehicleCounterStats)
async def get_stats(service: VehicleEventService = Depends(get_vc_service)):
    return await service.stats()


@router.get("/api/events", response_model=PaginatedResponse[VehicleEventResponse])
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: VehicleEventService = Depends(get_vc_service),
):
    """Paginated event list, newest first."""
    skip, limit = get_pagination_params(page, page_size)
    items = await service.repo.list_paginated(skip, limit)
    total = await service.repo.count()
    return build_paginated_response(items, total, page, limit)


@router.get("/api/events/export", include_in_schema=True)
async def export_events(
    start_date: Optional[str] = Query(
        None, description="IST date or datetime, e.g. 2026-08-01 or 2026-08-01T09:30"
    ),
    end_date: Optional[str] = Query(None, description="IST date or datetime"),
    service: VehicleEventService = Depends(get_vc_service),
):
    """Export events in a date range to .xlsx, oldest first."""
    start = _parse_bound(start_date, end_of_day=False)
    end = _parse_bound(end_date, end_of_day=True)

    events = await service.export_rows(start, end)

    headers = [
        "#", "Direction", "In Count", "Out Count", "Number Plate",
        "Date", "Time", "Recorded At",
    ]
    rows = []
    running_in = running_out = 0
    for event in events:
        running_in += event.in_count
        running_out += event.out_count
        local = _to_ist(event.timestamp)
        created = _to_ist(event.created_at)
        rows.append([
            event.id,
            event.direction,
            event.in_count,
            event.out_count,
            event.number_plate or "",
            local.strftime("%d/%m/%Y"),
            local.strftime("%I:%M:%S %p"),
            created.strftime("%d/%m/%Y %I:%M:%S %p") if created else "",
        ])

    # Totals row, so the file is self-contained without re-deriving sums.
    if rows:
        rows.append([])
        rows.append([
            "", "TOTAL", running_in, running_out, "",
            "Inside", str(running_in - running_out), "",
        ])

    output = generate_excel("Vehicle Log", headers, rows, "vehicle_log")
    stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f"attachment; filename=vehicle_log_{stamp}.xlsx"
        },
    )


@router.patch("/api/events/{event_id}", response_model=VehicleEventResponse)
async def update_event(
    event_id: int,
    body: VehicleEventUpdate,
    service: VehicleEventService = Depends(get_vc_service),
):
    """Inline edit. Patching ``direction`` re-derives in_count/out_count."""
    return await service.update_event(event_id, body.model_dump(exclude_unset=True))


@router.delete("/api/events/{event_id}", response_model=MessageResponse)
async def delete_event(
    event_id: int,
    service: VehicleEventService = Depends(get_vc_service),
):
    """Soft delete: the row disappears from listings and totals but is kept."""
    await service.delete_event(event_id)
    return MessageResponse(message="Event deleted successfully")
