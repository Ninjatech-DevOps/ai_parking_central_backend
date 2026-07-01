import uuid
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select as sa_select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, verify_location_in_scope
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.models.location import Location
from src.app.models.anpr_session import AnprSession
from src.app.repositories.anpr_session import AnprSessionRepository
from src.app.schemas.anpr_session import AnprSessionResponse, AnprSessionUpdate
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.services.anpr_session import AnprSessionService
from src.app.utils.export import generate_excel, generate_anpr_sessions_pdf
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/anpr-sessions", tags=["ANPR Sessions"])


def _ev(v) -> str:
    """Extract .value from enum, or return str as-is."""
    return v.value if hasattr(v, "value") else str(v)


def _get_service(db: AsyncSession = Depends(get_db)) -> AnprSessionService:
    return AnprSessionService(AnprSessionRepository(db))


async def _anpr_occupancy_summary(db, location_id, user_location_ids) -> dict:
    """Live occupancy via the config-slots model (same as anpr-dashboard):
      Total     = configured location slots (locations.total_*_slots)
      Occupied  = vehicles currently inside = active ANPR sessions (IN - OUT)
      Available = max(0, Total - Occupied)
    Single location -> that location; all -> summed across the scope.
    """
    loc_q = sa_select(
        func.coalesce(func.sum(Location.total_car_slots), 0),
        func.coalesce(func.sum(Location.total_two_wheeler_slots), 0),
    ).where(Location.is_active.is_(True))
    if location_id:
        loc_q = loc_q.where(Location.id == location_id)
    elif user_location_ids is not None:
        loc_q = loc_q.where(Location.id.in_(user_location_ids))
    car_total, bike_total = (await db.execute(loc_q)).one()

    sess_q = (
        sa_select(AnprSession.vehicle_type, func.count())
        .where(AnprSession.is_active.is_(True))
        .group_by(AnprSession.vehicle_type)
    )
    if location_id:
        sess_q = sess_q.where(AnprSession.location_id == location_id)
    elif user_location_ids is not None:
        sess_q = sess_q.where(AnprSession.location_id.in_(user_location_ids))
    car_occ = bike_occ = 0
    for vtype, count in (await db.execute(sess_q)).all():
        if _ev(vtype) == "CAR":
            car_occ = count
        elif _ev(vtype) == "TWO_WHEELER":
            bike_occ = count

    return {
        "car": {"total": car_total, "occupied": car_occ, "available": max(0, car_total - car_occ)},
        "bike": {"total": bike_total, "occupied": bike_occ, "available": max(0, bike_total - bike_occ)},
    }


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(date_str) if date_str else None


async def _resolve_scope(area_id, user_location_ids, db):
    if not area_id:
        return user_location_ids
    result = await db.execute(sa_select(Location.id).where(Location.area_id == area_id))
    area_loc_ids = {row[0] for row in result.all()}
    return (user_location_ids & area_loc_ids) if user_location_ids is not None else area_loc_ids


@router.get("", response_model=PaginatedResponse[AnprSessionResponse])
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    number_plate: Optional[str] = Query(None),
    vehicle_type: Optional[str] = Query(None, description="CAR or TWO_WHEELER"),
    is_active: Optional[bool] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: AnprSessionService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped_ids = await _resolve_scope(area_id, user_location_ids, db)

    skip, limit = get_pagination_params(page, page_size)
    start = _parse_date(start_date)
    end = _parse_date(end_date)

    items = await service.get_filtered(
        skip, limit, location_id, scoped_ids, number_plate, vehicle_type, is_active, start, end
    )
    total = await service.count_filtered(
        location_id, scoped_ids, number_plate, vehicle_type, is_active, start, end
    )

    response_items = []
    for session in items:
        resp = AnprSessionResponse.model_validate(session)
        resp.duration_display = AnprSessionService.format_duration(session.entry_time, session.exit_time)
        if session.location:
            resp.location_name = session.location.name
        response_items.append(resp)

    return build_paginated_response(response_items, total, page, limit)


@router.patch("/{session_id}", response_model=AnprSessionResponse)
async def update_session(
    session_id: uuid.UUID,
    body: AnprSessionUpdate,
    service: AnprSessionService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_CONFIGURE)),
):
    session = await service.update(session_id, body.model_dump(exclude_unset=True))
    if not session:
        from src.app.exceptions.base import NotFoundException
        raise NotFoundException(detail="Session not found")
    resp = AnprSessionResponse.model_validate(session)
    resp.duration_display = AnprSessionService.format_duration(session.entry_time, session.exit_time)
    if session.location:
        resp.location_name = session.location.name
    return resp


@router.get("/export-csv")
async def export_sessions_csv(
    location_id: Optional[uuid.UUID] = Query(None),
    number_plate: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: AnprSessionService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    start = _parse_date(start_date)
    end = _parse_date(end_date)

    items = await service.get_filtered(
        0, 50000, location_id, user_location_ids, number_plate, None, is_active, start, end
    )

    ist = timedelta(hours=5, minutes=30)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Time", "Number Plate", "Vehicle Type", "In Time", "Out Time",
        "Duration", "Status", "Location",
    ])
    for s in items:
        dt = s.entry_time + ist
        duration = AnprSessionService.format_duration(s.entry_time, s.exit_time)
        writer.writerow([
            dt.strftime("%d %b %Y"),
            dt.strftime("%I:%M %p"),
            s.number_plate,
            _ev(s.vehicle_type),
            (s.entry_time + ist).strftime("%d %b %Y, %I:%M %p"),
            (s.exit_time + ist).strftime("%d %b %Y, %I:%M %p") if s.exit_time else "",
            duration or "Active",
            "Active" if s.is_active else "Completed",
            s.location.name if s.location else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=anpr_sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"},
    )


@router.get("/export-excel")
async def export_sessions_excel(
    location_id: Optional[uuid.UUID] = Query(None),
    number_plate: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: AnprSessionService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    items = await service.get_filtered(
        0, 50000, location_id, user_location_ids, number_plate, None, is_active, start, end
    )

    ist = timedelta(hours=5, minutes=30)
    headers = ["Date", "Time", "Number Plate", "Vehicle Type", "In Time",
               "Out Time", "Duration", "Status", "Location"]
    rows = []
    for s in items:
        dt = s.entry_time + ist
        duration = AnprSessionService.format_duration(s.entry_time, s.exit_time)
        rows.append([
            dt.strftime("%d %b %Y"),
            dt.strftime("%I:%M %p"),
            s.number_plate,
            _ev(s.vehicle_type),
            (s.entry_time + ist).strftime("%d %b %Y, %I:%M %p"),
            (s.exit_time + ist).strftime("%d %b %Y, %I:%M %p") if s.exit_time else "",
            duration or "Active",
            "Active" if s.is_active else "Completed",
            s.location.name if s.location else "",
        ])

    output = generate_excel("ANPR Sessions", headers, rows, "anpr_sessions")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=anpr_sessions_{ts}.xlsx"},
    )


@router.get("/export-pdf")
async def export_sessions_pdf(
    location_id: Optional[uuid.UUID] = Query(None),
    number_plate: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: AnprSessionService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    items = await service.get_filtered(
        0, 5000, location_id, user_location_ids, number_plate, None, is_active, start, end
    )

    ist = timedelta(hours=5, minutes=30)
    # ANPR session rows (records table) — honour the selected date range.
    rows = []
    for s in items:
        is_car = _ev(s.vehicle_type) == "CAR"
        rows.append({
            "snapshot_url": s.entry_image_url or "",
            "location": s.location.name if s.location else "",
            "plate": s.number_plate or "N/A",
            "type": "Car" if is_car else "Two Wheeler",
            "date": (s.entry_time + ist).strftime("%d %b %Y"),
            "in": (s.entry_time + ist).strftime("%I:%M %p"),
            "out_date": (s.exit_time + ist).strftime("%d %b %Y") if s.exit_time else "Still Parked",
            "out_time": (s.exit_time + ist).strftime("%I:%M %p") if s.exit_time else "",
            "duration": AnprSessionService.format_duration(s.entry_time, s.exit_time) or "Active",
            "status": "Parked" if s.is_active else "Exited",
        })

    # Summary cards = live ANPR occupancy (config-slots model), independent of
    # the date range: Total = configured location slots, Occupied = vehicles
    # currently inside (active sessions = IN - OUT), Available = Total - Occupied.
    summary = await _anpr_occupancy_summary(db, location_id, user_location_ids)

    location_name = "All locations"
    if location_id:
        res = await db.execute(sa_select(Location.name).where(Location.id == location_id))
        location_name = res.scalar_one_or_none() or "All locations"

    status = f"Updated {(datetime.utcnow() + ist).strftime('%d %b %Y, %I:%M %p')}"
    meta = {
        "title": "ANPR Sessions Report",
        "location": location_name,
        "status": status,
        # Location column in the table only when reporting across locations.
        "show_location": location_id is None,
    }

    # Off the event loop (image downloads block) so the worker stays responsive.
    output = await run_in_threadpool(generate_anpr_sessions_pdf, meta, summary, rows)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=anpr_sessions_{ts}.pdf"},
    )


@router.delete("/{session_id}", response_model=MessageResponse)
async def delete_session(
    session_id: uuid.UUID,
    service: AnprSessionService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_CONFIGURE)),
):
    await service.repo.delete(session_id)
    return MessageResponse(message="Session deleted")
