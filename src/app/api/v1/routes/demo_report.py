"""Demo Report — comprehensive PDF showcasing AI Parking + ANPR for the
10 AM – 6 PM operating window.  Location-based, no date selection (always today).
The "closing snapshot" card uses the 6 PM data point.

GET /api/v1/demo-report/pdf  → StreamingResponse (application/pdf)
"""

import uuid
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, time as dt_time
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import (
    PermissionChecker,
    get_user_location_ids,
    verify_location_in_scope,
)
from src.app.core.constants import (
    DeviceStatus,
    Permission,
    SlotState,
    VehicleType,
)
from src.app.db.session import get_db
from src.app.models.anpr_record import AnprRecord
from src.app.models.anpr_session import AnprSession
from src.app.models.area import Area
from src.app.models.camera import Camera
from src.app.models.device import Device
from src.app.models.floor import Floor
from src.app.models.location import Location
from src.app.models.parking_scan import ParkingScan
from src.app.models.parking_slot import ParkingSlot
from src.app.models.slot_event import SlotEvent
from src.app.models.zone import Zone
from src.app.utils.demo_report_pdf import generate_demo_report_pdf

router = APIRouter(prefix="/demo-report", tags=["Demo Report"])

IST = timedelta(hours=5, minutes=30)

# Operating window (IST)
OP_START_HOUR = 10  # 10 AM IST
OP_END_HOUR = 18    # 6 PM IST


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _today_window() -> Tuple[datetime, datetime]:
    """Return UTC datetimes for today's 10 AM – 6 PM IST window."""
    today = date.today()
    start_ist = datetime.combine(today, dt_time(OP_START_HOUR, 0))
    end_ist = datetime.combine(today, dt_time(OP_END_HOUR, 0))
    return start_ist - IST, end_ist - IST  # convert to UTC


def _fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return (dt + IST).strftime("%d %b %Y, %I:%M %p")


def _fmt_time(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return (dt + IST).strftime("%I:%M %p")


def _fmt_hour(h: Optional[int]) -> str:
    if h is None:
        return "-"
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"


def _fmt_minutes(m) -> str:
    if m is None:
        return "-"
    if m < 1:
        return "<1m"
    if m < 60:
        return f"{round(m)}m"
    h = int(m // 60)
    mm = round(m % 60)
    return f"{h}h {mm}m" if mm else f"{h}h"


def _ev(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _format_duration(entry: Optional[datetime], exit_: Optional[datetime]) -> Optional[str]:
    if not entry or not exit_:
        return None
    minutes = int((exit_ - entry).total_seconds() / 60)
    if minutes < 0:
        return None
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if h else f"{m}m"


async def _resolve_scope(
    db: AsyncSession,
    area_id: Optional[uuid.UUID],
    user_location_ids: Optional[Set[uuid.UUID]],
) -> Optional[Set[uuid.UUID]]:
    if not area_id:
        return user_location_ids
    rows = await db.execute(select(Location.id).where(Location.area_id == area_id))
    area_ids = {r[0] for r in rows.all()}
    return (user_location_ids & area_ids) if user_location_ids is not None else area_ids


# ─────────────────────────────────────────────────────────────
# Data gathering — all scoped to 10am-6pm IST, per-location
# ─────────────────────────────────────────────────────────────
async def _get_locations(db: AsyncSession, scoped_ids, area_id, location_id) -> List[Location]:
    q = select(Location).where(Location.is_active.is_(True))
    if location_id:
        q = q.where(Location.id == location_id)
    elif area_id:
        q = q.where(Location.area_id == area_id)
    if scoped_ids is not None:
        q = q.where(Location.id.in_(scoped_ids))
    return list((await db.execute(q)).scalars().all())


async def _closing_snapshot_per_location(
    db: AsyncSession, locations: List[Location], end_utc: datetime,
) -> Dict[uuid.UUID, Dict[str, Any]]:
    """Get the last parking scan before 6pm for each location (closing snapshot)."""
    result = {}
    for loc in locations:
        q = (
            select(ParkingScan)
            .where(ParkingScan.location_id == loc.id, ParkingScan.recorded_at <= end_utc)
            .order_by(ParkingScan.recorded_at.desc())
            .limit(1)
        )
        scan = (await db.execute(q)).scalar_one_or_none()
        if scan:
            result[loc.id] = {
                "car_occupied": scan.car_occupied,
                "car_available": scan.car_available,
                "car_total": scan.car_total,
                "two_wheeler_occupied": scan.two_wheeler_occupied,
                "two_wheeler_available": scan.two_wheeler_available,
                "two_wheeler_total": scan.two_wheeler_total,
                "has_obstruction": scan.has_obstruction,
                "image_url": scan.image_url,
                "recorded_at": scan.recorded_at,
            }
        else:
            result[loc.id] = {
                "car_occupied": 0, "car_available": loc.total_car_slots,
                "car_total": loc.total_car_slots,
                "two_wheeler_occupied": 0, "two_wheeler_available": loc.total_two_wheeler_slots,
                "two_wheeler_total": loc.total_two_wheeler_slots,
                "has_obstruction": False, "image_url": None, "recorded_at": None,
            }
    return result


async def _hourly_scans_per_location(
    db: AsyncSession, locations: List[Location], start_utc: datetime, end_utc: datetime,
) -> Dict[uuid.UUID, List[Dict[str, Any]]]:
    """For each location, get one scan per hour (10am-6pm IST = 9 data points)."""
    result = {}
    for loc in locations:
        hourly = []
        for h in range(OP_START_HOUR, OP_END_HOUR + 1):
            hour_utc = datetime.combine(date.today(), dt_time(h, 0)) - IST
            # Get closest scan to each hour mark
            q = (
                select(ParkingScan)
                .where(
                    ParkingScan.location_id == loc.id,
                    ParkingScan.recorded_at >= hour_utc - timedelta(minutes=30),
                    ParkingScan.recorded_at <= hour_utc + timedelta(minutes=30),
                )
                .order_by(func.abs(func.extract("epoch", ParkingScan.recorded_at - hour_utc)))
                .limit(1)
            )
            scan = (await db.execute(q)).scalar_one_or_none()
            if scan:
                hourly.append({
                    "hour": h,
                    "car_occupied": scan.car_occupied,
                    "car_available": scan.car_available,
                    "car_total": scan.car_total,
                    "two_wheeler_occupied": scan.two_wheeler_occupied,
                    "two_wheeler_available": scan.two_wheeler_available,
                    "two_wheeler_total": scan.two_wheeler_total,
                    "total_occupied": scan.car_occupied + scan.two_wheeler_occupied,
                    "total_capacity": scan.car_total + scan.two_wheeler_total,
                })
            else:
                hourly.append({
                    "hour": h, "car_occupied": 0, "car_available": 0, "car_total": 0,
                    "two_wheeler_occupied": 0, "two_wheeler_available": 0, "two_wheeler_total": 0,
                    "total_occupied": 0, "total_capacity": 0,
                })
        result[loc.id] = hourly
    return result


async def _parking_sessions_in_window(
    db: AsyncSession, scoped_ids, start_utc: datetime, end_utc: datetime,
) -> List[Dict[str, Any]]:
    """Reconstruct parking sessions from slot events within 10am-6pm."""
    filters = [
        ParkingSlot.is_active.is_(True),
        SlotEvent.recorded_at >= start_utc,
        SlotEvent.recorded_at <= end_utc,
    ]
    if scoped_ids is not None:
        filters.append(Floor.location_id.in_(scoped_ids))

    next_time = func.lead(SlotEvent.recorded_at).over(
        partition_by=SlotEvent.parking_slot_id,
        order_by=SlotEvent.recorded_at.asc(),
    ).label("exit_time")
    next_prev_state = func.lead(SlotEvent.previous_state).over(
        partition_by=SlotEvent.parking_slot_id,
        order_by=SlotEvent.recorded_at.asc(),
    ).label("next_prev_state")

    cte = (
        select(
            SlotEvent.parking_slot_id,
            SlotEvent.new_state,
            SlotEvent.detected_vehicle_type,
            SlotEvent.recorded_at.label("entry_time"),
            next_time,
            next_prev_state,
            ParkingSlot.label.label("slot_label"),
            Camera.position_label.label("camera_label"),
            Location.id.label("location_id"),
            Location.name.label("location_name"),
            Area.name.label("area_name"),
        )
        .join(ParkingSlot, ParkingSlot.id == SlotEvent.parking_slot_id)
        .outerjoin(Camera, Camera.id == ParkingSlot.camera_id)
        .outerjoin(Zone, Zone.id == ParkingSlot.zone_id)
        .outerjoin(Floor, Floor.id == Zone.floor_id)
        .outerjoin(Location, Location.id == Floor.location_id)
        .outerjoin(Area, Area.id == Location.area_id)
        .where(*filters)
        .cte("ev")
    )

    q = (
        select(cte)
        .where(cte.c.new_state.in_([SlotState.VEHICLE, SlotState.OBSTRUCTED]))
        .order_by(cte.c.entry_time.desc())
        .limit(50000)
    )
    rows = (await db.execute(q)).all()

    sessions = []
    for row in rows:
        exit_time = row.exit_time if row.next_prev_state == row.new_state else None
        duration = round((exit_time - row.entry_time).total_seconds() / 60, 1) if exit_time else None
        sessions.append({
            "slot_label": row.slot_label,
            "camera_label": row.camera_label,
            "location_id": row.location_id,
            "location_name": row.location_name,
            "area_name": row.area_name,
            "event_type": row.new_state,
            "detected_vehicle_type": row.detected_vehicle_type,
            "entry_time": row.entry_time,
            "exit_time": exit_time,
            "duration_minutes": duration,
            "is_active": exit_time is None,
            "hour": (row.entry_time + IST).hour,
        })
    return sessions


def _compute_parking_summary(sessions: List[Dict[str, Any]], op_hours: range) -> Dict[str, Any]:
    """Compute summary stats from parking sessions, restricted to operating hours."""
    if not sessions:
        return {
            "total_sessions": 0, "active_sessions": 0, "completed_sessions": 0,
            "vehicle_sessions": 0, "obstructed_sessions": 0,
            "car_sessions": 0, "two_wheeler_sessions": 0,
            "avg_duration_minutes": None, "max_duration_minutes": None,
            "min_duration_minutes": None,
            "peak_hour": None, "peak_hour_count": 0,
            "hourly_distribution": {h: 0 for h in op_hours},
            "duration_distribution": {"under_30m": 0, "30m_to_1h": 0, "1h_to_2h": 0, "2h_to_8h": 0, "over_8h": 0},
        }

    total = len(sessions)
    active = sum(1 for s in sessions if s["is_active"])
    vehicles = sum(1 for s in sessions if s["event_type"] == SlotState.VEHICLE)
    cars = sum(1 for s in sessions if s.get("detected_vehicle_type") == "CAR")
    tw = sum(1 for s in sessions if s.get("detected_vehicle_type") == "TWO_WHEELER")

    durations = [s["duration_minutes"] for s in sessions if s["duration_minutes"] is not None]

    hourly = {h: 0 for h in op_hours}
    for s in sessions:
        h = s["hour"]
        if h in hourly:
            hourly[h] += 1

    peak_count = max(hourly.values()) if hourly else 0
    peak_hour = max(hourly, key=hourly.get) if peak_count > 0 else None

    dur_dist = {"under_30m": 0, "30m_to_1h": 0, "1h_to_2h": 0, "2h_to_8h": 0, "over_8h": 0}
    for d in durations:
        if d < 30:
            dur_dist["under_30m"] += 1
        elif d < 60:
            dur_dist["30m_to_1h"] += 1
        elif d < 120:
            dur_dist["1h_to_2h"] += 1
        elif d < 480:
            dur_dist["2h_to_8h"] += 1
        else:
            dur_dist["over_8h"] += 1

    return {
        "total_sessions": total, "active_sessions": active,
        "completed_sessions": total - active,
        "vehicle_sessions": vehicles, "obstructed_sessions": total - vehicles,
        "car_sessions": cars, "two_wheeler_sessions": tw,
        "avg_duration_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "max_duration_minutes": round(max(durations), 1) if durations else None,
        "min_duration_minutes": round(min(durations), 1) if durations else None,
        "peak_hour": peak_hour, "peak_hour_count": peak_count,
        "hourly_distribution": hourly,
        "duration_distribution": dur_dist,
    }


def _parking_summary_per_location(sessions: List[Dict[str, Any]], op_hours: range) -> Dict[uuid.UUID, Dict[str, Any]]:
    """Group sessions by location and compute per-location summary."""
    by_loc: Dict[uuid.UUID, List] = defaultdict(list)
    for s in sessions:
        if s["location_id"]:
            by_loc[s["location_id"]].append(s)
    return {loc_id: _compute_parking_summary(loc_sessions, op_hours) for loc_id, loc_sessions in by_loc.items()}


async def _anpr_sessions_in_window(
    db: AsyncSession, scoped_ids, start_utc: datetime, end_utc: datetime,
) -> List[Dict[str, Any]]:
    """ANPR sessions that started within 10am-6pm."""
    q = (
        select(AnprSession, Location.name.label("location_name"))
        .outerjoin(Location, Location.id == AnprSession.location_id)
        .where(AnprSession.entry_time >= start_utc, AnprSession.entry_time <= end_utc)
    )
    if scoped_ids is not None:
        q = q.where(AnprSession.location_id.in_(scoped_ids))
    q = q.order_by(AnprSession.entry_time.desc()).limit(50000)

    out = []
    for s, location_name in (await db.execute(q)).all():
        out.append({
            "id": str(s.id),
            "location_id": s.location_id,
            "number_plate": s.number_plate,
            "vehicle_type": _ev(s.vehicle_type),
            "entry_time": s.entry_time,
            "exit_time": s.exit_time,
            "entry_image_url": s.entry_image_url,
            "exit_image_url": s.exit_image_url,
            "is_active": s.is_active,
            "duration_display": _format_duration(s.entry_time, s.exit_time),
            "location_name": location_name,
        })
    return out


def _anpr_analytics(sessions: List[Dict[str, Any]], op_hours: range) -> Dict[str, Any]:
    """Aggregate ANPR sessions for 10am-6pm."""
    total = len(sessions)
    durations = []
    hourly = {h: 0 for h in op_hours}
    plate_counts: Counter = Counter()
    loc_counts: Counter = Counter()
    cars = tw = inside = exits = 0

    for s in sessions:
        et = s["entry_time"]
        xt = s["exit_time"]
        if et:
            h = (et + IST).hour
            if h in hourly:
                hourly[h] += 1
        if xt and et:
            exits += 1
            dmin = (xt - et).total_seconds() / 60
            if dmin >= 0:
                durations.append(dmin)
        if s["vehicle_type"] == "CAR":
            cars += 1
        elif s["vehicle_type"] == "TWO_WHEELER":
            tw += 1
        if s["is_active"] or not s["exit_time"]:
            inside += 1
        plate_counts[s["number_plate"]] += 1
        loc_counts[s["location_name"] or "Unknown"] += 1

    peak = max(hourly.values()) if hourly else 0
    peak_hour = max(hourly, key=hourly.get) if peak > 0 else None

    return {
        "entries": total, "exits": exits, "inside": inside,
        "cars": cars, "two_wheelers": tw,
        "unique_plates": len(plate_counts),
        "avg_dur": round(sum(durations) / len(durations), 1) if durations else None,
        "max_dur": round(max(durations), 1) if durations else None,
        "hourly": hourly,
        "peak_hour": peak_hour, "peak_count": peak,
        "top_plates": [{"label": k, "count": v} for k, v in plate_counts.most_common(8)],
        "top_locations": [{"label": k, "count": v} for k, v in loc_counts.most_common(8)],
        "duration_distribution": _anpr_dur_dist(durations),
    }


def _anpr_dur_dist(durations: List[float]) -> Dict[str, int]:
    dist = {"under_30m": 0, "30m_to_1h": 0, "1h_to_2h": 0, "2h_to_8h": 0, "over_8h": 0}
    for d in durations:
        if d < 30:
            dist["under_30m"] += 1
        elif d < 60:
            dist["30m_to_1h"] += 1
        elif d < 120:
            dist["1h_to_2h"] += 1
        elif d < 480:
            dist["2h_to_8h"] += 1
        else:
            dist["over_8h"] += 1
    return dist


def _anpr_per_location(sessions: List[Dict[str, Any]], op_hours: range) -> Dict[uuid.UUID, Dict[str, Any]]:
    by_loc: Dict[uuid.UUID, List] = defaultdict(list)
    for s in sessions:
        if s["location_id"]:
            by_loc[s["location_id"]].append(s)
    return {loc_id: _anpr_analytics(loc_sessions, op_hours) for loc_id, loc_sessions in by_loc.items()}


async def _anpr_closing_snapshot(
    db: AsyncSession, locations: List[Location], end_utc: datetime, scoped_ids,
) -> Dict[uuid.UUID, Dict[str, Any]]:
    """ANPR occupancy at 6pm — count of active sessions at that time per location."""
    result = {}
    for loc in locations:
        # Sessions that started before 6pm and either still active or exited after 6pm
        q = (
            select(AnprSession.vehicle_type, func.count())
            .where(
                AnprSession.location_id == loc.id,
                AnprSession.entry_time <= end_utc,
                (AnprSession.exit_time.is_(None)) | (AnprSession.exit_time > end_utc),
            )
            .group_by(AnprSession.vehicle_type)
        )
        car_inside = tw_inside = 0
        for vtype, count in (await db.execute(q)).all():
            if vtype == VehicleType.CAR:
                car_inside = count
            elif vtype == VehicleType.TWO_WHEELER:
                tw_inside = count
        result[loc.id] = {
            "car_inside": car_inside,
            "tw_inside": tw_inside,
            "car_total": loc.total_car_slots,
            "tw_total": loc.total_two_wheeler_slots,
        }
    return result


async def _device_summary(db, scoped_ids) -> Dict[str, int]:
    q = select(Device.status, func.count()).where(Device.is_active.is_(True)).group_by(Device.status)
    if scoped_ids is not None:
        q = q.where(Device.location_id.in_(scoped_ids))
    summary = {"total": 0, "online": 0, "offline": 0}
    for status, count in (await db.execute(q)).all():
        summary["total"] += count
        if status == DeviceStatus.ONLINE:
            summary["online"] += count
        else:
            summary["offline"] += count
    return summary


async def _slot_counts(db, scoped_ids) -> Dict[str, int]:
    q = (
        select(ParkingSlot.state, func.count())
        .join(Zone, Zone.id == ParkingSlot.zone_id)
        .join(Floor, Floor.id == Zone.floor_id)
        .where(ParkingSlot.is_active.is_(True))
        .group_by(ParkingSlot.state)
    )
    if scoped_ids is not None:
        q = q.where(Floor.location_id.in_(scoped_ids))
    counts = {"total": 0, "available": 0, "occupied": 0, "obstructed": 0}
    for state, count in (await db.execute(q)).all():
        counts["total"] += count
        if state == SlotState.EMPTY:
            counts["available"] += count
        elif state == SlotState.VEHICLE:
            counts["occupied"] += count
        elif state == SlotState.OBSTRUCTED:
            counts["obstructed"] += count
    return counts


async def _anpr_records_in_window(
    db: AsyncSession, scoped_ids, start_utc: datetime, end_utc: datetime,
) -> List[Dict[str, Any]]:
    """ANPR raw records (plate reads) in window — for confidence stats."""
    q = (
        select(
            AnprRecord.number_plate, AnprRecord.vehicle_type, AnprRecord.direction,
            AnprRecord.confidence_gemini, AnprRecord.confidence_paddle,
            AnprRecord.gemini_result, AnprRecord.paddle_result,
            AnprRecord.recorded_at, AnprRecord.image_url,
            Location.name.label("location_name"),
        )
        .outerjoin(Location, Location.id == AnprRecord.location_id)
        .where(AnprRecord.recorded_at >= start_utc, AnprRecord.recorded_at <= end_utc)
    )
    if scoped_ids is not None:
        q = q.where(AnprRecord.location_id.in_(scoped_ids))
    q = q.order_by(AnprRecord.recorded_at.desc()).limit(10000)

    out = []
    for r in (await db.execute(q)).all():
        out.append({
            "number_plate": r.number_plate,
            "vehicle_type": _ev(r.vehicle_type),
            "direction": _ev(r.direction),
            "confidence_gemini": r.confidence_gemini,
            "confidence_paddle": r.confidence_paddle,
            "gemini_result": r.gemini_result,
            "paddle_result": r.paddle_result,
            "recorded_at": r.recorded_at,
            "image_url": r.image_url,
            "location_name": r.location_name,
        })
    return out


def _ocr_confidence_stats(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute OCR confidence distribution from ANPR records."""
    gemini_scores = [r["confidence_gemini"] for r in records if r["confidence_gemini"] is not None]
    paddle_scores = [r["confidence_paddle"] for r in records if r["confidence_paddle"] is not None]
    match_count = sum(
        1 for r in records
        if r["gemini_result"] and r["paddle_result"]
        and r["gemini_result"] == r["paddle_result"]
    )
    both = sum(1 for r in records if r["gemini_result"] and r["paddle_result"])
    return {
        "total_reads": len(records),
        "gemini_avg": round(sum(gemini_scores) / len(gemini_scores) * 100, 1) if gemini_scores else None,
        "paddle_avg": round(sum(paddle_scores) / len(paddle_scores) * 100, 1) if paddle_scores else None,
        "gemini_min": round(min(gemini_scores) * 100, 1) if gemini_scores else None,
        "gemini_max": round(max(gemini_scores) * 100, 1) if gemini_scores else None,
        "paddle_min": round(min(paddle_scores) * 100, 1) if paddle_scores else None,
        "paddle_max": round(max(paddle_scores) * 100, 1) if paddle_scores else None,
        "dual_match_rate": round(match_count / both * 100, 1) if both > 0 else None,
        "in_count": sum(1 for r in records if r["direction"] == "IN"),
        "out_count": sum(1 for r in records if r["direction"] == "OUT"),
    }


# ─────────────────────────────────────────────────────────────
# API endpoint
# ─────────────────────────────────────────────────────────────
@router.get("/pdf")
async def download_demo_report_pdf(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Generate and download the demo report PDF (10 AM – 6 PM, today)."""
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped = await _resolve_scope(db, area_id, user_location_ids)

    start_utc, end_utc = _today_window()
    op_hours = range(OP_START_HOUR, OP_END_HOUR + 1)
    today_str = date.today().strftime("%d %B %Y")

    # Gather all data
    locations = await _get_locations(db, scoped, area_id, location_id)
    closing = await _closing_snapshot_per_location(db, locations, end_utc)
    hourly_scans = await _hourly_scans_per_location(db, locations, start_utc, end_utc)

    parking_sessions = await _parking_sessions_in_window(db, scoped, start_utc, end_utc)
    parking_summary = _compute_parking_summary(parking_sessions, op_hours)
    parking_by_loc = _parking_summary_per_location(parking_sessions, op_hours)

    anpr_sessions = await _anpr_sessions_in_window(db, scoped, start_utc, end_utc)
    anpr_summary = _anpr_analytics(anpr_sessions, op_hours)
    anpr_by_loc = _anpr_per_location(anpr_sessions, op_hours)
    anpr_closing = await _anpr_closing_snapshot(db, locations, end_utc, scoped)

    anpr_records = await _anpr_records_in_window(db, scoped, start_utc, end_utc)
    ocr_stats = _ocr_confidence_stats(anpr_records)

    slot_counts = await _slot_counts(db, scoped)
    dev_summary = await _device_summary(db, scoped)

    # Build per-location data for the PDF
    loc_data = []
    for loc in locations:
        lid = loc.id
        cs = closing.get(lid, {})
        hs = hourly_scans.get(lid, [])
        ps = parking_by_loc.get(lid)
        ans = anpr_by_loc.get(lid)
        ac = anpr_closing.get(lid, {})
        loc_data.append({
            "name": loc.name,
            "address": loc.address or "",
            "car_capacity": loc.total_car_slots,
            "tw_capacity": loc.total_two_wheeler_slots,
            "total_capacity": loc.total_car_slots + loc.total_two_wheeler_slots,
            "closing_snapshot": cs,
            "hourly_scans": hs,
            "parking_summary": ps or _compute_parking_summary([], op_hours),
            "anpr_summary": ans or _anpr_analytics([], op_hours),
            "anpr_closing": ac,
        })

    # Session rows for tables
    parking_table_rows = [{
        "slot_label": s["slot_label"] or "",
        "location_name": s["location_name"] or "",
        "type": "Obstructed" if s["event_type"] == SlotState.OBSTRUCTED else "Vehicle",
        "vehicle": s.get("detected_vehicle_type") or "-",
        "entry": _fmt_dt(s["entry_time"]),
        "exit": _fmt_dt(s["exit_time"]),
        "duration": _fmt_minutes(s["duration_minutes"]),
        "status": ("Blocked" if s["event_type"] == SlotState.OBSTRUCTED else "Parked") if s["is_active"] else ("Cleared" if s["event_type"] == SlotState.OBSTRUCTED else "Completed"),
    } for s in parking_sessions[:200]]

    anpr_table_rows = [{
        "plate": s["number_plate"],
        "type": "Car" if s["vehicle_type"] == "CAR" else "2-Wheeler",
        "location": s["location_name"] or "-",
        "entry": _fmt_dt(s["entry_time"]),
        "exit": _fmt_dt(s["exit_time"]),
        "duration": s["duration_display"] or "Active",
        "status": "Inside" if (s["is_active"] or not s["exit_time"]) else "Exited",
    } for s in anpr_sessions[:200]]

    # Build the PDF data dict
    pdf_data = {
        "date": today_str,
        "operating_hours": f"{_fmt_hour(OP_START_HOUR)} - {_fmt_hour(OP_END_HOUR)}",
        "op_start": OP_START_HOUR,
        "op_end": OP_END_HOUR,
        "locations": loc_data,
        "global": {
            "slot_counts": slot_counts,
            "device_summary": dev_summary,
            "parking_summary": parking_summary,
            "anpr_summary": anpr_summary,
            "ocr_stats": ocr_stats,
            "total_locations": len(locations),
            "total_capacity": sum(l.total_car_slots + l.total_two_wheeler_slots for l in locations),
        },
        "parking_sessions": parking_table_rows,
        "anpr_sessions": anpr_table_rows,
    }

    output = generate_demo_report_pdf(pdf_data)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=demo_report_{ts}.pdf"},
    )
