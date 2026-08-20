"""Routes for the vehicle counter module.

Mounted at the top level (``/vehicle-counter``) rather than under ``/api/v1``:
a future blanket auth dependency on ``api_v1_router`` is a plausible one-line
change that would silently break this module, and these routes read a different
database entirely.

Every ``/api`` route requires a token from ``/api/auth/login`` (a single shared
password, see ``auth.py``). The ``?edit`` / ``?delete`` / ``?export`` URL params
remain a UI affordance only -- they shape what the page shows, while the token
is what actually controls access.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.utils.export import generate_excel
from src.app.utils.pagination import build_paginated_response, get_pagination_params
from src.app.exceptions.base import BadRequestException
from src.app.vehicle_counter.auth import authenticate, require_counter_auth
from src.app.vehicle_counter.db import get_vc_db
from src.app.vehicle_counter.repository import VehicleEventRepository
from src.app.vehicle_counter.schemas import (
    CounterPageData,
    LoginRequest,
    LoginResponse,
    VehicleCounterStats,
    VehicleEventCreate,
    VehicleEventResponse,
    VehicleEventUpdate,
)
from src.app.vehicle_counter.service import VehicleEventService

# Single source of truth for the module's URL prefix. Change it here only --
# main.py derives the static mount from it, and the page derives its asset and
# API URLs from its own location, so nothing else hardcodes the path.
URL_PREFIX = "/aadawefr-dfcaw-wdww"

router = APIRouter(prefix=URL_PREFIX, tags=["Vehicle Counter"])

STATIC_DIR = Path(__file__).parent / "static"
STATIC_URL = f"{URL_PREFIX}/static"


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


# Human-readable labels for the spreadsheet, which is read by people rather
# than parsed by code.
_TYPE_LABELS = {"CAR": "Car", "TWO_WHEELER": "2 Wheeler"}


def _normalize_type_filter(value: Optional[str]) -> Optional[str]:
    """Normalize an optional vehicle_type filter.

    Empty string and "ALL" both mean no filter, so the UI can send its select
    value through unchanged.
    """
    if not value:
        return None
    normalized = value.strip().upper()
    if normalized in ("", "ALL"):
        return None
    if normalized not in ("CAR", "TWO_WHEELER"):
        raise BadRequestException(
            detail="vehicle_type must be 'CAR' or 'TWO_WHEELER'"
        )
    return normalized


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
    """Redirect to the trailing-slash form.

    The page references its assets relatively ("static/app.css"), which only
    resolve correctly when the URL ends in a slash -- without it the browser
    would look for the assets one level up.
    """
    return RedirectResponse(url=f"{URL_PREFIX}/", status_code=307)


@router.get("/", include_in_schema=False)
async def counter_page():
    return _page("index.html")


# --- Auth ----------------------------------------------------------------

# Unguarded: this is how a token is obtained in the first place.
auth_router = APIRouter(prefix="/api/auth", tags=["Vehicle Counter"])


@auth_router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Exchange the shared password for a long-lived token."""
    token = authenticate(body.password)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in_days=settings.VEHICLE_COUNTER_TOKEN_EXPIRE_DAYS,
    )


@auth_router.get("/me", response_model=MessageResponse)
async def whoami(subject: str = Depends(require_counter_auth)):
    """Cheap token check the page calls on load to pick which view to show."""
    return MessageResponse(message=subject)


# --- API -----------------------------------------------------------------

# Every route below inherits the auth guard. Declaring it on the router rather
# than per-handler is fail-closed: a new endpoint added here is protected by
# default instead of only when someone remembers to add the dependency.
api = APIRouter(
    prefix="/api",
    tags=["Vehicle Counter"],
    dependencies=[Depends(require_counter_auth)],
)


@api.post("/events", response_model=VehicleEventResponse, status_code=201)
async def create_event(
    body: VehicleEventCreate,
    service: VehicleEventService = Depends(get_vc_service),
):
    """Record one IN or OUT button press for a vehicle type."""
    return await service.record(body.direction, body.vehicle_type, body.timestamp)


@api.get("/summary", response_model=CounterPageData)
async def get_summary(
    recent_limit: int = Query(10, ge=1, le=50),
    service: VehicleEventService = Depends(get_vc_service),
):
    """Stats plus the most recent events -- the counter page payload."""
    return CounterPageData(
        stats=await service.stats(),
        recent=await service.repo.recent(recent_limit),
    )


@api.get("/stats", response_model=VehicleCounterStats)
async def get_stats(service: VehicleEventService = Depends(get_vc_service)):
    return await service.stats()


@api.get("/events", response_model=PaginatedResponse[VehicleEventResponse])
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    vehicle_type: Optional[str] = Query(None, description="CAR or TWO_WHEELER"),
    start_date: Optional[str] = Query(None, description="IST date or datetime"),
    end_date: Optional[str] = Query(None, description="IST date or datetime"),
    service: VehicleEventService = Depends(get_vc_service),
):
    """Paginated event list, newest first."""
    vtype = _normalize_type_filter(vehicle_type)
    start = _parse_bound(start_date, end_of_day=False)
    end = _parse_bound(end_date, end_of_day=True)

    skip, limit = get_pagination_params(page, page_size)
    items = await service.repo.list_paginated(skip, limit, vtype, start, end)
    # Same filters as the list, or the pager would offer empty pages.
    total = await service.repo.count(vtype, start, end)
    return build_paginated_response(items, total, page, limit)


@api.get("/events/export", include_in_schema=True)
async def export_events(
    start_date: Optional[str] = Query(
        None, description="IST date or datetime, e.g. 2026-08-01 or 2026-08-01T09:30"
    ),
    end_date: Optional[str] = Query(None, description="IST date or datetime"),
    vehicle_type: Optional[str] = Query(None, description="CAR or TWO_WHEELER"),
    service: VehicleEventService = Depends(get_vc_service),
):
    """Export events in a date range to .xlsx, oldest first."""
    start = _parse_bound(start_date, end_of_day=False)
    end = _parse_bound(end_date, end_of_day=True)
    vtype = _normalize_type_filter(vehicle_type)

    events = await service.export_rows(start, end, vtype)

    headers = [
        "#", "Vehicle Type", "Direction", "In Count", "Out Count",
        "Number Plate", "Date", "Time", "Recorded At",
    ]
    rows = []
    # Accumulate per type so the totals block mirrors the on-screen columns.
    tally = {"CAR": [0, 0], "TWO_WHEELER": [0, 0]}
    for event in events:
        bucket = tally.setdefault(event.vehicle_type, [0, 0])
        bucket[0] += event.in_count
        bucket[1] += event.out_count
        local = _to_ist(event.timestamp)
        created = _to_ist(event.created_at)
        rows.append([
            event.id,
            _TYPE_LABELS.get(event.vehicle_type, event.vehicle_type),
            event.direction,
            event.in_count,
            event.out_count,
            event.number_plate or "",
            local.strftime("%d/%m/%Y"),
            local.strftime("%I:%M:%S %p"),
            created.strftime("%d/%m/%Y %I:%M:%S %p") if created else "",
        ])

    # Totals block, so the file is self-contained without re-deriving sums.
    if rows:
        car_in, car_out = tally["CAR"]
        tw_in, tw_out = tally["TWO_WHEELER"]
        rows.append([])
        rows.append(["", "Car", "TOTAL", car_in, car_out,
                     "", "Inside", car_in - car_out, ""])
        rows.append(["", "2 Wheeler", "TOTAL", tw_in, tw_out,
                     "", "Inside", tw_in - tw_out, ""])
        rows.append(["", "Overall", "TOTAL", car_in + tw_in, car_out + tw_out,
                     "", "Inside", (car_in + tw_in) - (car_out + tw_out), ""])

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


@api.patch("/events/{event_id}", response_model=VehicleEventResponse)
async def update_event(
    event_id: int,
    body: VehicleEventUpdate,
    service: VehicleEventService = Depends(get_vc_service),
):
    """Inline edit. Patching ``direction`` re-derives in_count/out_count."""
    return await service.update_event(event_id, body.model_dump(exclude_unset=True))


@api.delete("/events/{event_id}", response_model=MessageResponse)
async def delete_event(
    event_id: int,
    service: VehicleEventService = Depends(get_vc_service),
):
    """Soft delete: the row disappears from listings and totals but is kept."""
    await service.delete_event(event_id)
    return MessageResponse(message="Event deleted successfully")


# --- Assembly ------------------------------------------------------------
# auth_router first: /api/auth/login must not inherit the guard that `api`
# carries, or there would be no way to obtain a token.
router.include_router(auth_router)
router.include_router(api)
