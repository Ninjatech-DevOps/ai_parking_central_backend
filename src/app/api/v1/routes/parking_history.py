import uuid
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession as SA_AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, verify_location_in_scope
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.models.location import Location as LocationModel
from src.app.repositories.parking_scan import ParkingScanRepository
from src.app.schemas.parking_scan import ParkingScanResponse, ParkingScanUpdate
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.services.parking_scan import ParkingScanService
from src.app.utils.export import generate_excel, generate_parking_history_pdf
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/parking-history", tags=["Parking History"])

IST = timedelta(hours=5, minutes=30)


def _get_service(db: AsyncSession = Depends(get_db)) -> ParkingScanService:
    return ParkingScanService(ParkingScanRepository(db))


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(date_str) if date_str else None


def _fmt_date(dt: datetime) -> str:
    return (dt + IST).strftime("%d %b %Y")


def _fmt_time(dt: datetime) -> str:
    ist_dt = dt + IST
    # Round to nearest 5 minutes
    minute = ist_dt.minute
    rounded = ((minute + 2) // 5) * 5
    if rounded == 60:
        ist_dt = ist_dt.replace(minute=0) + timedelta(hours=1)
    else:
        ist_dt = ist_dt.replace(minute=rounded)
    return ist_dt.strftime("%I:%M %p")


def _clean_frame_url(url: Optional[str]) -> str:
    """Prefer the 'clean' frame (slot polylines only) over the debug frame
    (which also draws vehicle-detection boxes/labels). The edge uploads both:
    `debug/{device}/{camera}/latest.jpg` (debug) and `.../clean.jpg` (clean)."""
    if url and url.endswith("/latest.jpg"):
        return url[: -len("/latest.jpg")] + "/clean.jpg"
    return url or ""


@router.get("", response_model=PaginatedResponse[ParkingScanResponse])
async def list_scans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval_minutes: Optional[int] = Query(None, ge=0, le=60, description="Sample interval in minutes (0=all rows, 5=one per 5min)"),
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)

    # Narrow scope by area
    scoped_ids = user_location_ids
    if area_id:
        result = await db.execute(select(LocationModel.id).where(LocationModel.area_id == area_id))
        area_loc_ids = {row[0] for row in result.all()}
        scoped_ids = (scoped_ids & area_loc_ids) if scoped_ids is not None else area_loc_ids

    skip, limit = get_pagination_params(page, page_size)
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    iv = interval_minutes if interval_minutes and interval_minutes > 0 else None

    items = await service.get_filtered(
        skip, limit, location_id, scoped_ids, start, end, iv
    )
    total = await service.count_filtered(
        location_id, scoped_ids, start, end, iv
    )

    response_items = []
    for scan in items:
        resp = ParkingScanResponse.model_validate(scan)
        if scan.location:
            resp.location_name = scan.location.name
        if scan.camera:
            resp.camera_label = scan.camera.position_label
        if scan.device:
            resp.device_name = scan.device.device_id
        response_items.append(resp)

    return build_paginated_response(response_items, total, page, limit)


async def _resolve_scope(area_id, user_location_ids, db):
    if not area_id:
        return user_location_ids
    result = await db.execute(select(LocationModel.id).where(LocationModel.area_id == area_id))
    area_loc_ids = {row[0] for row in result.all()}
    return (user_location_ids & area_loc_ids) if user_location_ids is not None else area_loc_ids


@router.get("/occupancy-summary")
async def get_occupancy_summary(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    """Current occupancy summary cards for the AI Parking History page.

    Same logic as the parking PDF: take each location's latest scan, then sum
    across scope. Single location -> that location's last entry; all -> sum of
    every location's last entry. Honors the page's Area / Location filters.
    """
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped_ids = await _resolve_scope(area_id, user_location_ids, db)

    summary = await service.current_occupancy_summary(location_id, scoped_ids)
    car = summary["car"]
    bike = summary["bike"]
    recorded_at = summary.get("latest_recorded_at")

    location_name = "All locations"
    if location_id:
        loc = await db.execute(select(LocationModel.name).where(LocationModel.id == location_id))
        location_name = loc.scalar_one_or_none() or "All locations"

    return {
        "location_name": location_name,
        "location_count": summary["location_count"],
        "car_total": car["total"],
        "car_occupied": car["occupied"],
        "car_available": car["available"],
        "two_wheeler_total": bike["total"],
        "two_wheeler_occupied": bike["occupied"],
        "two_wheeler_available": bike["available"],
        "updated_at": (recorded_at + IST).strftime("%d %b %Y, %I:%M %p") if recorded_at else None,
    }


@router.get("/export-csv")
async def export_scans_csv(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval_minutes: Optional[int] = Query(None, ge=0, le=60),
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    scoped_ids = await _resolve_scope(area_id, user_location_ids, db)
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    iv = interval_minutes if interval_minutes and interval_minutes > 0 else None
    items = await service.get_filtered(
        0, 50000, location_id, scoped_ids, start, end, iv
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Time", "Car Occupied", "Car Available", "Car Total",
        "2W Occupied", "2W Available", "2W Total", "Obstruction", "Location",
    ])
    for s in items:
        writer.writerow([
            _fmt_date(s.recorded_at),
            _fmt_time(s.recorded_at),
            s.car_occupied, s.car_available, s.car_total,
            s.two_wheeler_occupied, s.two_wheeler_available, s.two_wheeler_total,
            "Yes" if s.has_obstruction else "No",
            s.location.name if s.location else "",
        ])

    output.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=parking_history_{ts}.csv"},
    )


@router.get("/export-excel")
async def export_scans_excel(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval_minutes: Optional[int] = Query(None, ge=0, le=60),
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    scoped_ids = await _resolve_scope(area_id, user_location_ids, db)
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    iv = interval_minutes if interval_minutes and interval_minutes > 0 else None
    items = await service.get_filtered(
        0, 50000, location_id, scoped_ids, start, end, iv
    )

    headers = ["Date", "Time", "Car Occupied", "Car Available", "Car Total",
               "2W Occupied", "2W Available", "2W Total", "Obstruction", "Location"]
    rows = []
    for s in items:
        rows.append([
            _fmt_date(s.recorded_at),
            _fmt_time(s.recorded_at),
            s.car_occupied, s.car_available, s.car_total,
            s.two_wheeler_occupied, s.two_wheeler_available, s.two_wheeler_total,
            "Yes" if s.has_obstruction else "No",
            s.location.name if s.location else "",
        ])

    output = generate_excel("Parking History", headers, rows, "parking_history")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=parking_history_{ts}.xlsx"},
    )


@router.get("/export-pdf")
async def export_scans_pdf(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval_minutes: Optional[int] = Query(None, ge=0, le=60),
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    scoped_ids = await _resolve_scope(area_id, user_location_ids, db)
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    iv = interval_minutes if interval_minutes and interval_minutes > 0 else None
    items = await service.get_filtered(
        0, 5000, location_id, scoped_ids, start, end, iv
    )

    # Occupancy records (one row per scan). Use the clean frame for thumbnails.
    rows = []
    for s in items:
        rows.append({
            "snapshot_url": _clean_frame_url(s.image_url),
            "location": s.location.name if s.location else "",
            "date": _fmt_date(s.recorded_at),
            "time": _fmt_time(s.recorded_at),
            "occ_car": s.car_occupied,
            "avl_car": s.car_available,
            "tot_car": s.car_total,
            "occ_bike": s.two_wheeler_occupied,
            "avl_bike": s.two_wheeler_available,
            "tot_bike": s.two_wheeler_total,
        })

    # Summary cards = each location's latest scan, summed across scope.
    # Single location -> that location's last entry; all -> sum of every
    # location's latest entry (shared ParkingScanService.current_occupancy_summary).
    summary = await service.current_occupancy_summary(location_id, scoped_ids)
    recorded_at = summary.get("latest_recorded_at")

    location_name = "All locations"
    if location_id:
        loc = await db.execute(select(LocationModel.name).where(LocationModel.id == location_id))
        location_name = loc.scalar_one_or_none() or "All locations"

    meta = {
        "title": "Parking Occupancy Report",
        "location": location_name,
        "status": f"Updated {_fmt_date(recorded_at)}, {_fmt_time(recorded_at)}" if recorded_at else "No data",
        # Location column only makes sense across multiple locations; for a single
        # selected location it's redundant (already shown in the subtitle).
        "show_location": location_id is None,
    }

    # Build hourly data (10AM-6PM) for bar chart — pick closest scan to each hour
    hourly_data = []
    for h in range(10, 19):  # 10 AM to 6 PM
        best = None
        best_diff = float("inf")
        for s in items:
            if s.recorded_at:
                ist_hour = (s.recorded_at + IST).hour
                ist_min = (s.recorded_at + IST).minute
                diff = abs((ist_hour * 60 + ist_min) - h * 60)
                if diff < best_diff and diff <= 30:  # within 30 min window
                    best_diff = diff
                    best = s
        hourly_data.append({
            "hour": h,
            "occ_car": best.car_occupied if best else 0,
            "tot_car": best.car_total if best else 0,
            "occ_bike": best.two_wheeler_occupied if best else 0,
            "tot_bike": best.two_wheeler_total if best else 0,
        })

    # Run PDF generation (which downloads images, blocking) off the event loop
    # so the single-worker server stays responsive (login, etc.) during export.
    output = await run_in_threadpool(generate_parking_history_pdf, meta, summary, rows, hourly_data)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=parking_history_{ts}.pdf"},
    )


@router.patch("/{scan_id}", response_model=ParkingScanResponse)
async def update_scan(
    scan_id: uuid.UUID,
    body: ParkingScanUpdate,
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
):
    """Update parking scan numbers (inline edit from FE)."""
    data = body.model_dump(exclude_unset=True)
    scan = await service.update_scan(scan_id, data)
    resp = ParkingScanResponse.model_validate(scan)
    if scan.location:
        resp.location_name = scan.location.name
    if scan.camera:
        resp.camera_label = scan.camera.position_label
    if scan.device:
        resp.device_name = scan.device.device_id
    return resp


@router.delete("/{scan_id}", response_model=MessageResponse)
async def delete_scan(
    scan_id: uuid.UUID,
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
):
    await service.repo.delete(scan_id)
    return MessageResponse(message="Scan deleted")
