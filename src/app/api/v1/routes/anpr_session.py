import uuid
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, verify_location_in_scope
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.anpr_session import AnprSessionRepository
from src.app.schemas.anpr_session import AnprSessionResponse
from src.app.schemas.base import PaginatedResponse
from src.app.services.anpr_session import AnprSessionService
from src.app.utils.export import generate_excel, generate_pdf_with_images
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/anpr-sessions", tags=["ANPR Sessions"])


def _ev(v) -> str:
    """Extract .value from enum, or return str as-is."""
    return v.value if hasattr(v, "value") else str(v)


def _get_service(db: AsyncSession = Depends(get_db)) -> AnprSessionService:
    return AnprSessionService(AnprSessionRepository(db))


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(date_str) if date_str else None


@router.get("", response_model=PaginatedResponse[AnprSessionResponse])
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    location_id: Optional[uuid.UUID] = Query(None),
    number_plate: Optional[str] = Query(None),
    vehicle_type: Optional[str] = Query(None, description="CAR or TWO_WHEELER"),
    is_active: Optional[bool] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: AnprSessionService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)

    skip, limit = get_pagination_params(page, page_size)
    start = _parse_date(start_date)
    end = _parse_date(end_date)

    items = await service.get_filtered(
        skip, limit, location_id, user_location_ids, number_plate, vehicle_type, is_active, start, end
    )
    total = await service.count_filtered(
        location_id, user_location_ids, number_plate, vehicle_type, is_active, start, end
    )

    response_items = []
    for session in items:
        resp = AnprSessionResponse.model_validate(session)
        resp.duration_display = AnprSessionService.format_duration(session.entry_time, session.exit_time)
        if session.location:
            resp.location_name = session.location.name
        response_items.append(resp)

    return build_paginated_response(response_items, total, page, limit)


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
):
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    items = await service.get_filtered(
        0, 5000, location_id, user_location_ids, number_plate, None, is_active, start, end
    )

    ist = timedelta(hours=5, minutes=30)
    records = []
    for s in items:
        duration = AnprSessionService.format_duration(s.entry_time, s.exit_time)
        records.append({
            "image_url": s.entry_image_url or "",
            "fields": [
                ("Number Plate", s.number_plate),
                ("Vehicle Type", _ev(s.vehicle_type)),
                ("Date", (s.entry_time + ist).strftime("%d %b %Y")),
                ("In Time", (s.entry_time + ist).strftime("%I:%M %p")),
                ("Out Time", (s.exit_time + ist).strftime("%d %b %Y, %I:%M %p") if s.exit_time else "Still Parked"),
                ("Duration", duration or "Active"),
                ("Status", "Active" if s.is_active else "Completed"),
                ("Location", s.location.name if s.location else "-"),
            ],
        })

    output = generate_pdf_with_images("ANPR Sessions Report", records)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=anpr_sessions_{ts}.pdf"},
    )
