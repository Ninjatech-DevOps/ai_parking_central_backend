import uuid
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession as SA_AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, verify_location_in_scope
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.models.location import Location as LocationModel
from src.app.repositories.parking_scan import ParkingScanRepository
from src.app.schemas.parking_scan import ParkingScanResponse
from src.app.schemas.base import PaginatedResponse
from src.app.services.parking_scan import ParkingScanService
from src.app.utils.export import generate_excel, generate_pdf_with_images
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
    return (dt + IST).strftime("%I:%M %p")


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

    items = await service.get_filtered(
        skip, limit, location_id, scoped_ids, start, end
    )
    total = await service.count_filtered(
        location_id, scoped_ids, start, end
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


@router.get("/export-csv")
async def export_scans_csv(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    scoped_ids = await _resolve_scope(area_id, user_location_ids, db)
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    items = await service.get_filtered(
        0, 50000, location_id, scoped_ids, start, end
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
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    scoped_ids = await _resolve_scope(area_id, user_location_ids, db)
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    items = await service.get_filtered(
        0, 50000, location_id, scoped_ids, start, end
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
    service: ParkingScanService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    scoped_ids = await _resolve_scope(area_id, user_location_ids, db)
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    items = await service.get_filtered(
        0, 5000, location_id, scoped_ids, start, end
    )

    records = []
    for s in items:
        records.append({
            # Use the clean frame (slot polylines only) — not the debug frame
            # which also overlays vehicle-detection boxes on cars.
            "image_url": _clean_frame_url(s.image_url),
            "fields": [
                ("Date", _fmt_date(s.recorded_at)),
                ("Time", _fmt_time(s.recorded_at)),
                ("Location", s.location.name if s.location else "-"),
                ("Camera", s.camera.position_label if s.camera else "-"),
                ("Car Occupied", str(s.car_occupied)),
                ("Car Available", str(s.car_available)),
                ("Car Total", str(s.car_total)),
                ("2-Wheeler Occupied", str(s.two_wheeler_occupied)),
                ("2-Wheeler Available", str(s.two_wheeler_available)),
                ("2-Wheeler Total", str(s.two_wheeler_total)),
            ],
        })

    output = generate_pdf_with_images("AI Parking History Report", records)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=parking_history_{ts}.pdf"},
    )
