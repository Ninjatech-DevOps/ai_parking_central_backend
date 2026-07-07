import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import VehicleType, SlotState
from src.app.db.session import get_db
from src.app.models.anpr_session import AnprSession
from src.app.models.floor import Floor
from src.app.models.location import Location
from src.app.models.parking_slot import ParkingSlot
from src.app.models.zone import Zone
from src.app.repositories.anpr_record import AnprRecordRepository
from src.app.repositories.anpr_session import AnprSessionRepository
from src.app.repositories.camera import CameraRepository
from src.app.repositories.device import DeviceRepository
from src.app.repositories.location import LocationRepository
from src.app.repositories.parking_scan import ParkingScanRepository
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.repositories.shared_link import SharedLinkRepository
from src.app.schemas.anpr_record import AnprRecordResponse
from src.app.schemas.anpr_session import AnprSessionResponse
from src.app.schemas.base import PaginatedResponse
from src.app.schemas.parking_scan import ParkingScanResponse
from src.app.schemas.shared_link import PublicViewResponse
from src.app.services.shared_link import SharedLinkService
from src.app.services.anpr_analytics import session_revenue, build_anpr_report
from src.app.services.parking_analytics import build_parking_report
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/public", tags=["Public View"])


def get_shared_link_service(db: AsyncSession = Depends(get_db)) -> SharedLinkService:
    return SharedLinkService(
        shared_link_repo=SharedLinkRepository(db),
        location_repo=LocationRepository(db),
        device_repo=DeviceRepository(db),
        camera_repo=CameraRepository(db),
        slot_repo=ParkingSlotRepository(db),
    )


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(date_str) if date_str else None


@router.get("/view/{token}", response_model=PublicViewResponse)
async def get_public_view(
    token: str,
    service: SharedLinkService = Depends(get_shared_link_service),
):
    return await service.resolve_public_view(token)


@router.get("/view/{token}/parking-history", response_model=PaginatedResponse[ParkingScanResponse])
async def get_public_parking_history(
    token: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval_minutes: Optional[int] = Query(None),
    service: SharedLinkService = Depends(get_shared_link_service),
    db: AsyncSession = Depends(get_db),
):
    link = await service.validate_public_link(token, required_page="parking_history")
    location_ids = await service._resolve_location_ids(link)
    location_id_set = set(location_ids) if location_ids else set()

    repo = ParkingScanRepository(db)
    skip, limit = get_pagination_params(page, page_size)
    start = _parse_date(start_date)
    end = _parse_date(end_date)

    items = await repo.get_filtered(
        skip, limit, location_ids=location_id_set or None,
        start_date=start, end_date=end, interval_minutes=interval_minutes,
    )
    total = await repo.count_filtered(
        location_ids=location_id_set or None,
        start_date=start, end_date=end, interval_minutes=interval_minutes,
    )

    response_items = []
    for scan in items:
        resp = ParkingScanResponse.model_validate(scan)
        if scan.location:
            resp.location_name = scan.location.name
        if scan.device:
            resp.device_name = getattr(scan.device, "device_id", None)
        response_items.append(resp)

    return build_paginated_response(response_items, total, page, limit)


@router.get("/view/{token}/parking-history/occupancy-summary")
async def get_public_occupancy_summary(
    token: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: SharedLinkService = Depends(get_shared_link_service),
    db: AsyncSession = Depends(get_db),
):
    link = await service.validate_public_link(token, required_page="parking_history")
    location_ids = await service._resolve_location_ids(link)
    location_id_set = set(location_ids) if location_ids else set()

    # Report — windowed hourly occupancy (10 AM-6 PM) + summary stats, mirroring
    # the AI Parking Occupancy PDF. Window defaults to today when unset.
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    repo = ParkingScanRepository(db)
    report_items = await repo.get_filtered(
        0, 5000, location_ids=location_id_set or None,
        start_date=start, end_date=end,
    )
    report = build_parking_report(report_items)

    # Summary cards = latest scan in the filtered window (same as PDF export).
    if report_items:
        latest = report_items[0]  # sorted desc by recorded_at
        return {
            "car_occupied": latest.car_occupied or 0,
            "car_available": latest.car_available or 0,
            "car_total": latest.car_total or 0,
            "two_wheeler_occupied": latest.two_wheeler_occupied or 0,
            "two_wheeler_available": latest.two_wheeler_available or 0,
            "two_wheeler_total": latest.two_wheeler_total or 0,
            "report": report,
        }

    return {
        "car_occupied": 0, "car_available": 0, "car_total": 0,
        "two_wheeler_occupied": 0, "two_wheeler_available": 0, "two_wheeler_total": 0,
        "report": report,
    }


@router.get("/view/{token}/anpr-records", response_model=PaginatedResponse[AnprRecordResponse])
async def get_public_anpr_records(
    token: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    number_plate: Optional[str] = Query(None),
    vehicle_type: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: SharedLinkService = Depends(get_shared_link_service),
    db: AsyncSession = Depends(get_db),
):
    link = await service.validate_public_link(token, required_page="anpr_records")
    location_ids = await service._resolve_location_ids(link)
    location_id_set = set(location_ids) if location_ids else set()

    repo = AnprRecordRepository(db)
    skip, limit = get_pagination_params(page, page_size)
    start = _parse_date(start_date)
    end = _parse_date(end_date)

    items = await repo.get_filtered(
        skip, limit, location_ids=location_id_set or None,
        number_plate=number_plate, vehicle_type=vehicle_type,
        direction=direction, start_date=start, end_date=end,
    )
    total = await repo.count_filtered(
        location_ids=location_id_set or None,
        number_plate=number_plate, vehicle_type=vehicle_type,
        direction=direction, start_date=start, end_date=end,
    )

    response_items = []
    for record in items:
        resp = AnprRecordResponse.model_validate(record)
        if record.location:
            resp.location_name = record.location.name
        response_items.append(resp)

    return build_paginated_response(response_items, total, page, limit)


@router.get("/view/{token}/anpr-sessions", response_model=PaginatedResponse[AnprSessionResponse])
async def get_public_anpr_sessions(
    token: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    number_plate: Optional[str] = Query(None),
    vehicle_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: SharedLinkService = Depends(get_shared_link_service),
    db: AsyncSession = Depends(get_db),
):
    link = await service.validate_public_link(token, required_page="anpr_history")
    location_ids = await service._resolve_location_ids(link)
    location_id_set = set(location_ids) if location_ids else set()

    repo = AnprSessionRepository(db)
    skip, limit = get_pagination_params(page, page_size)
    start = _parse_date(start_date)
    end = _parse_date(end_date)

    items = await repo.get_filtered(
        skip, limit, location_ids=location_id_set or None,
        number_plate=number_plate, vehicle_type=vehicle_type,
        is_active=is_active, start_date=start, end_date=end,
    )
    total = await repo.count_filtered(
        location_ids=location_id_set or None,
        number_plate=number_plate, vehicle_type=vehicle_type,
        is_active=is_active, start_date=start, end_date=end,
    )

    response_items = []
    for session in items:
        resp = AnprSessionResponse.model_validate(session)
        if session.location:
            resp.location_name = session.location.name
        # Compute duration display
        if session.entry_time and session.exit_time:
            delta = session.exit_time - session.entry_time
            total_min = int(delta.total_seconds() / 60)
            if total_min < 60:
                resp.duration_display = f"{total_min}m"
            else:
                h = total_min // 60
                m = total_min % 60
                resp.duration_display = f"{h}h {m}m" if m else f"{h}h"
        # Revenue (Rs) — realised only once the vehicle has exited.
        resp.revenue = f"{session_revenue(session.entry_time, session.exit_time):,}" if session.exit_time else "-"
        response_items.append(resp)

    return build_paginated_response(response_items, total, page, limit)


@router.get("/view/{token}/anpr-dashboard")
async def get_public_anpr_dashboard(
    token: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    service: SharedLinkService = Depends(get_shared_link_service),
    db: AsyncSession = Depends(get_db),
):
    # Allow access from both dashboard_anpr and anpr_history pages
    try:
        link = await service.validate_public_link(token, required_page="dashboard_anpr")
    except Exception:
        link = await service.validate_public_link(token, required_page="anpr_history")
    location_ids = await service._resolve_location_ids(link)
    location_id_set = set(location_ids) if location_ids else None

    # Get location totals
    loc_q = select(
        func.coalesce(func.sum(Location.total_car_slots), 0).label("car_total"),
        func.coalesce(func.sum(Location.total_two_wheeler_slots), 0).label("tw_total"),
    ).where(
        Location.is_active == True,
        (Location.total_car_slots > 0) | (Location.total_two_wheeler_slots > 0),
    )
    if location_id_set:
        loc_q = loc_q.where(Location.id.in_(location_id_set))
    loc_row = (await db.execute(loc_q)).one()
    car_total = loc_row.car_total
    tw_total = loc_row.tw_total

    # Count active sessions by vehicle type
    session_q = (
        select(AnprSession.vehicle_type, func.count().label("count"))
        .where(AnprSession.is_active == True)
        .group_by(AnprSession.vehicle_type)
    )
    if location_id_set:
        session_q = session_q.where(AnprSession.location_id.in_(location_id_set))
    session_rows = (await db.execute(session_q)).all()

    car_occupied = 0
    tw_occupied = 0
    for vtype, count in session_rows:
        if vtype == VehicleType.CAR:
            car_occupied = count
        elif vtype == VehicleType.TWO_WHEELER:
            tw_occupied = count

    # Count obstructions
    obs_q = (
        select(func.count())
        .select_from(ParkingSlot)
        .join(Zone, Zone.id == ParkingSlot.zone_id)
        .join(Floor, Floor.id == Zone.floor_id)
        .where(ParkingSlot.is_active == True, ParkingSlot.state == SlotState.OBSTRUCTED)
    )
    if location_id_set:
        obs_q = obs_q.where(Floor.location_id.in_(location_id_set))
    obstructions = (await db.execute(obs_q)).scalar_one()

    # Get location breakdown
    loc_detail_q = select(Location).where(
        Location.is_active == True,
        (Location.total_car_slots > 0) | (Location.total_two_wheeler_slots > 0),
    )
    if location_id_set:
        loc_detail_q = loc_detail_q.where(Location.id.in_(location_id_set))
    locations = (await db.execute(loc_detail_q)).scalars().all()

    active_counts = await AnprSessionRepository(db).count_active_by_location(
        location_ids=location_id_set,
    )
    occ_map = {}
    for row in active_counts:
        lid = row["location_id"]
        if lid not in occ_map:
            occ_map[lid] = {}
        occ_map[lid][row["vehicle_type"]] = row["count"]

    loc_result = []
    for loc in locations:
        occ = occ_map.get(loc.id, {})
        c_occ = occ.get(VehicleType.CAR, 0)
        t_occ = occ.get(VehicleType.TWO_WHEELER, 0)
        c_total = loc.total_car_slots
        t_total = loc.total_two_wheeler_slots
        total = c_total + t_total
        occupied = c_occ + t_occ
        loc_result.append({
            "location_id": str(loc.id),
            "location_name": loc.name,
            "car_total": c_total,
            "car_occupied": c_occ,
            "car_available": max(0, c_total - c_occ),
            "two_wheeler_total": t_total,
            "two_wheeler_occupied": t_occ,
            "two_wheeler_available": max(0, t_total - t_occ),
            "occupancy_pct": round((occupied / total * 100), 1) if total > 0 else 0,
        })

    # ANPR report — windowed cards (Total/In/Out/Available + Occupancy %,
    # Revenue Rs, Accuracy %) and charts (In/Out pattern + Duration breakdown),
    # mirroring the ANPR Sessions PDF. Window defaults to today when unset.
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    report_items = await AnprSessionRepository(db).get_filtered(
        0, 5000, location_ids=location_id_set, start_date=start, end_date=end,
    )
    report = await build_anpr_report(db, location_id_set, report_items, start, end)

    return {
        "summary": {
            "car_total": car_total,
            "car_occupied": car_occupied,
            "car_available": max(0, car_total - car_occupied),
            "two_wheeler_total": tw_total,
            "two_wheeler_occupied": tw_occupied,
            "two_wheeler_available": max(0, tw_total - tw_occupied),
            "obstructions": obstructions,
        },
        "locations": loc_result,
        "report": report,
    }
