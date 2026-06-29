"""Reports page API — self-contained, page-driven analytics for the frontend
Reports screen (Overview / AI Parking / ANPR / Peak Occupancy + unified export).

This module is intentionally self-contained: it builds its own queries (parking
sessions, summary, ANPR, occupancy heatmap) and does not depend on the shared
slot-event / ANPR services. Reused only: ORM models and the Excel/CSV helpers.

The whole router is hidden from Swagger (registered with include_in_schema=False
in api/v1/__init__.py) but remains fully functional.
"""

import csv
import io
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
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
    AlertSeverity,
    AlertStatus,
    DeviceStatus,
    Permission,
    SlotState,
    VehicleType,
)
from src.app.db.session import get_db
from src.app.models.alert_event import AlertEvent
from src.app.models.anpr_session import AnprSession
from src.app.models.area import Area
from src.app.models.camera import Camera
from src.app.models.city import City
from src.app.models.device import Device
from src.app.models.floor import Floor
from src.app.models.location import Location
from src.app.models.parking_slot import ParkingSlot
from src.app.models.slot_event import SlotEvent
from src.app.models.zone import Zone
from src.app.utils.export import generate_excel_multi, generate_report_pdf

router = APIRouter(prefix="/reports", tags=["Reports"])

IST = timedelta(hours=5, minutes=30)


# ─────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────
def _parse_date(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


async def _resolve_scope(
    db: AsyncSession,
    area_id: Optional[uuid.UUID],
    user_location_ids: Optional[Set[uuid.UUID]],
) -> Optional[Set[uuid.UUID]]:
    """Narrow the user's allowed location IDs by an optional area filter."""
    if not area_id:
        return user_location_ids
    rows = await db.execute(select(Location.id).where(Location.area_id == area_id))
    area_ids = {r[0] for r in rows.all()}
    return (user_location_ids & area_ids) if user_location_ids is not None else area_ids


def _fmt_dt(dt: Optional[datetime]) -> str:
    return (dt + IST).strftime("%d %b %Y, %I:%M %p") if dt else ""


def _format_duration(entry: Optional[datetime], exit_: Optional[datetime]) -> Optional[str]:
    if not entry or not exit_:
        return None
    minutes = int((exit_ - entry).total_seconds() / 60)
    if minutes < 0:
        return None
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _ev(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


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


def _fmt_hour(h) -> str:
    if h is None:
        return "-"
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"


def _anpr_analytics(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate ANPR sessions the same way the frontend's aggregateAnpr() does."""
    total = len(sessions)
    durations = []
    hourly = [0] * 24
    plate_counts: Counter = Counter()
    loc_counts: Counter = Counter()
    cars = tw = inside = exits = 0
    for s in sessions:
        et = datetime.fromisoformat(s["entry_time"]) if s["entry_time"] else None
        xt = datetime.fromisoformat(s["exit_time"]) if s["exit_time"] else None
        if et:
            hourly[(et + IST).hour] += 1
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
    peak = max(hourly) if hourly else 0
    return {
        "entries": total, "exits": exits, "inside": inside, "cars": cars, "two_wheelers": tw,
        "unique_plates": len(plate_counts),
        "avg_dur": round(sum(durations) / len(durations), 1) if durations else None,
        "max_dur": round(max(durations), 1) if durations else None,
        "hourly": hourly,
        "peak_hour": hourly.index(peak) if peak > 0 else None,
        "top_plates": [{"label": k, "count": v} for k, v in plate_counts.most_common(8)],
        "top_locations": [{"label": k, "count": v} for k, v in loc_counts.most_common(8)],
    }


# ─────────────────────────────────────────────────────────────
# AI Parking — sessions + summary
# ─────────────────────────────────────────────────────────────
async def _build_parking_sessions(
    db: AsyncSession,
    scoped_ids: Optional[Set[uuid.UUID]],
    area_id: Optional[uuid.UUID],
    location_id: Optional[uuid.UUID],
    camera_id: Optional[uuid.UUID],
    status: Optional[str],
    event_type: Optional[str],
    start: Optional[datetime],
    end: Optional[datetime],
) -> List[Dict[str, Any]]:
    """Reconstruct parking sessions from slot_events using a LEAD() window."""
    filters = [ParkingSlot.is_active.is_(True)]
    if scoped_ids is not None:
        filters.append(Floor.location_id.in_(scoped_ids))
    if area_id:
        filters.append(Location.area_id == area_id)
    if location_id:
        filters.append(Floor.location_id == location_id)
    if camera_id:
        filters.append(ParkingSlot.camera_id == camera_id)
    if start:
        filters.append(SlotEvent.recorded_at >= start)
    if end:
        filters.append(SlotEvent.recorded_at <= end)

    next_time = func.lead(SlotEvent.recorded_at).over(
        partition_by=SlotEvent.parking_slot_id,
        order_by=SlotEvent.recorded_at.asc(),
    ).label("exit_time")
    next_prev_state = func.lead(SlotEvent.previous_state).over(
        partition_by=SlotEvent.parking_slot_id,
        order_by=SlotEvent.recorded_at.asc(),
    ).label("next_prev_state")

    events_cte = (
        select(
            SlotEvent.parking_slot_id,
            SlotEvent.new_state,
            SlotEvent.detected_vehicle_type,
            SlotEvent.recorded_at.label("entry_time"),
            next_time,
            next_prev_state,
            ParkingSlot.label.label("slot_label"),
            Camera.position_label.label("camera_label"),
            Location.name.label("location_name"),
            Area.name.label("area_name"),
            City.name.label("city_name"),
        )
        .join(ParkingSlot, ParkingSlot.id == SlotEvent.parking_slot_id)
        .outerjoin(Camera, Camera.id == ParkingSlot.camera_id)
        .outerjoin(Zone, Zone.id == ParkingSlot.zone_id)
        .outerjoin(Floor, Floor.id == Zone.floor_id)
        .outerjoin(Location, Location.id == Floor.location_id)
        .outerjoin(Area, Area.id == Location.area_id)
        .outerjoin(City, City.id == Location.city_id)
        .where(*filters)
        .cte("events_with_lead")
    )

    session_q = (
        select(events_cte)
        .where(events_cte.c.new_state.in_([SlotState.VEHICLE, SlotState.OBSTRUCTED]))
        .order_by(events_cte.c.entry_time.desc())
        .limit(50000)
    )
    rows = (await db.execute(session_q)).all()

    sessions: List[Dict[str, Any]] = []
    for row in rows:
        entry_time = row.entry_time
        exit_time = row.exit_time if row.next_prev_state == row.new_state else None
        duration = round((exit_time - entry_time).total_seconds() / 60, 1) if exit_time else None
        sessions.append({
            "slot_label": row.slot_label,
            "camera_label": row.camera_label,
            "location_name": row.location_name,
            "area_name": row.area_name,
            "city_name": row.city_name,
            "event_type": row.new_state,
            "detected_vehicle_type": row.detected_vehicle_type,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "duration_minutes": duration,
            "is_active": exit_time is None,
            "hour": (entry_time + IST).hour,
        })

    # Post-filters mirroring the frontend's status/type mapping.
    if status == "parked":
        sessions = [s for s in sessions if s["is_active"]]
    elif status == "completed":
        sessions = [s for s in sessions if not s["is_active"]]
    if event_type in (SlotState.VEHICLE, SlotState.OBSTRUCTED):
        sessions = [s for s in sessions if s["event_type"] == event_type]

    return sessions


def _compute_parking_summary(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not sessions:
        return {
            "total_sessions": 0, "active_sessions": 0, "completed_sessions": 0,
            "vehicle_sessions": 0, "obstructed_sessions": 0,
            "car_sessions": 0, "two_wheeler_sessions": 0,
            "avg_duration_minutes": None, "max_duration_minutes": None, "min_duration_minutes": None,
            "peak_hour": None, "peak_hour_count": 0,
            "hourly_distribution": [0] * 24,
            "duration_distribution": {"under_30m": 0, "30m_to_1h": 0, "1h_to_2h": 0, "2h_to_8h": 0, "over_8h": 0},
            "top_slots": [], "unique_slots": 0,
        }

    total = len(sessions)
    active = sum(1 for s in sessions if s["is_active"])
    vehicles = sum(1 for s in sessions if s["event_type"] == SlotState.VEHICLE)
    car = sum(1 for s in sessions if s.get("detected_vehicle_type") == "CAR")
    tw = sum(1 for s in sessions if s.get("detected_vehicle_type") == "TWO_WHEELER")

    durations = [s["duration_minutes"] for s in sessions if s["duration_minutes"] is not None]
    hourly = [0] * 24
    for s in sessions:
        hourly[s["hour"]] += 1
    peak_count = max(hourly)

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

    slot_counts = Counter(s["slot_label"] for s in sessions)
    top_slots = [{"label": label, "count": count} for label, count in slot_counts.most_common(10)]

    return {
        "total_sessions": total,
        "active_sessions": active,
        "completed_sessions": total - active,
        "vehicle_sessions": vehicles,
        "obstructed_sessions": total - vehicles,
        "car_sessions": car,
        "two_wheeler_sessions": tw,
        "avg_duration_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "max_duration_minutes": round(max(durations), 1) if durations else None,
        "min_duration_minutes": round(min(durations), 1) if durations else None,
        "peak_hour": hourly.index(peak_count) if peak_count > 0 else None,
        "peak_hour_count": peak_count,
        "hourly_distribution": hourly,
        "duration_distribution": dur_dist,
        "top_slots": top_slots,
        "unique_slots": len(slot_counts),
    }


async def _slot_counts(db, scoped_ids, location_id) -> Dict[str, int]:
    q = (
        select(ParkingSlot.state, func.count())
        .join(Zone, Zone.id == ParkingSlot.zone_id)
        .join(Floor, Floor.id == Zone.floor_id)
        .where(ParkingSlot.is_active.is_(True))
        .group_by(ParkingSlot.state)
    )
    if scoped_ids is not None:
        q = q.where(Floor.location_id.in_(scoped_ids))
    elif location_id:
        q = q.where(Floor.location_id == location_id)
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


async def _device_summary(db, scoped_ids, location_id) -> Dict[str, int]:
    q = select(Device.status, func.count()).where(Device.is_active.is_(True)).group_by(Device.status)
    if scoped_ids is not None:
        q = q.where(Device.location_id.in_(scoped_ids))
    elif location_id:
        q = q.where(Device.location_id == location_id)
    summary = {"total": 0, "online": 0, "offline": 0}
    for status, count in (await db.execute(q)).all():
        summary["total"] += count
        if status == DeviceStatus.ONLINE:
            summary["online"] += count
        else:
            summary["offline"] += count
    return summary


async def _alert_summary(db, scoped_ids, location_id, start, end) -> Dict[str, int]:
    q = select(AlertEvent.severity, AlertEvent.status, func.count()).group_by(
        AlertEvent.severity, AlertEvent.status
    )
    if scoped_ids is not None:
        q = q.where(AlertEvent.location_id.in_(scoped_ids))
    elif location_id:
        q = q.where(AlertEvent.location_id == location_id)
    if start:
        q = q.where(AlertEvent.created_at >= start)
    if end:
        q = q.where(AlertEvent.created_at <= end)
    summary = {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0, "active": 0, "resolved": 0}
    for severity, status, count in (await db.execute(q)).all():
        summary["total"] += count
        if severity == AlertSeverity.CRITICAL:
            summary["critical"] += count
        elif severity == AlertSeverity.HIGH:
            summary["high"] += count
        elif severity == AlertSeverity.MEDIUM:
            summary["medium"] += count
        else:
            summary["low"] += count
        if status == AlertStatus.ACTIVE:
            summary["active"] += count
        elif status == AlertStatus.RESOLVED:
            summary["resolved"] += count
    return summary


async def _report_payload(
    db, scoped_ids, area_id, location_id, camera_id, status, event_type, start, end,
) -> Dict[str, Any]:
    sessions = await _build_parking_sessions(
        db, scoped_ids, area_id, location_id, camera_id, status, event_type, start, end
    )
    summary = _compute_parking_summary(sessions)
    formatted = [{
        "slot_label": s["slot_label"],
        "camera_label": s["camera_label"],
        "location_name": s["location_name"],
        "area_name": s["area_name"],
        "city_name": s["city_name"],
        "event_type": s["event_type"],
        "detected_vehicle_type": s.get("detected_vehicle_type"),
        "entry_time": s["entry_time"].isoformat(),
        "exit_time": s["exit_time"].isoformat() if s["exit_time"] else None,
        "duration_minutes": s["duration_minutes"],
        "is_active": s["is_active"],
    } for s in sessions[:500]]
    return {
        "summary": summary,
        "slot_counts": await _slot_counts(db, scoped_ids, location_id),
        "device_summary": await _device_summary(db, scoped_ids, location_id),
        "alert_summary": await _alert_summary(db, scoped_ids, location_id, start, end),
        "sessions": formatted,
        "total_sessions_in_period": len(sessions),
        "_raw_sessions": sessions,  # internal: used by export, stripped before JSON
    }


# ─────────────────────────────────────────────────────────────
# ANPR (fresh, report-page-specific)
# ─────────────────────────────────────────────────────────────
async def _anpr_summary(db, scoped_ids, location_id) -> Dict[str, Any]:
    loc_q = select(
        func.coalesce(func.sum(Location.total_car_slots), 0),
        func.coalesce(func.sum(Location.total_two_wheeler_slots), 0),
    ).where(Location.is_active.is_(True))
    if location_id:
        loc_q = loc_q.where(Location.id == location_id)
    elif scoped_ids is not None:
        loc_q = loc_q.where(Location.id.in_(scoped_ids))
    car_total, tw_total = (await db.execute(loc_q)).one()

    sess_q = (
        select(AnprSession.vehicle_type, func.count())
        .where(AnprSession.is_active.is_(True))
        .group_by(AnprSession.vehicle_type)
    )
    if location_id:
        sess_q = sess_q.where(AnprSession.location_id == location_id)
    elif scoped_ids is not None:
        sess_q = sess_q.where(AnprSession.location_id.in_(scoped_ids))
    car_occ = tw_occ = 0
    for vtype, count in (await db.execute(sess_q)).all():
        if vtype == VehicleType.CAR:
            car_occ = count
        elif vtype == VehicleType.TWO_WHEELER:
            tw_occ = count

    obs_q = (
        select(func.count()).select_from(ParkingSlot)
        .join(Zone, Zone.id == ParkingSlot.zone_id)
        .join(Floor, Floor.id == Zone.floor_id)
        .where(ParkingSlot.is_active.is_(True), ParkingSlot.state == SlotState.OBSTRUCTED)
    )
    if location_id:
        obs_q = obs_q.where(Floor.location_id == location_id)
    elif scoped_ids is not None:
        obs_q = obs_q.where(Floor.location_id.in_(scoped_ids))
    obstructions = (await db.execute(obs_q)).scalar_one()

    return {
        "car_total": car_total,
        "car_occupied": car_occ,
        "car_available": max(0, car_total - car_occ),
        "two_wheeler_total": tw_total,
        "two_wheeler_occupied": tw_occ,
        "two_wheeler_available": max(0, tw_total - tw_occ),
        "obstructions": obstructions,
    }


async def _anpr_locations(db, scoped_ids, area_id, location_id) -> List[Dict[str, Any]]:
    loc_q = select(Location).where(Location.is_active.is_(True))
    if location_id:
        loc_q = loc_q.where(Location.id == location_id)
    elif area_id:
        loc_q = loc_q.where(Location.area_id == area_id)
    if scoped_ids is not None:
        loc_q = loc_q.where(Location.id.in_(scoped_ids))
    locations = (await db.execute(loc_q)).scalars().all()

    sess_q = (
        select(AnprSession.location_id, AnprSession.vehicle_type, func.count())
        .where(AnprSession.is_active.is_(True))
        .group_by(AnprSession.location_id, AnprSession.vehicle_type)
    )
    if scoped_ids is not None:
        sess_q = sess_q.where(AnprSession.location_id.in_(scoped_ids))
    occ_map: Dict[uuid.UUID, Dict[Any, int]] = defaultdict(dict)
    for loc_id, vtype, count in (await db.execute(sess_q)).all():
        occ_map[loc_id][vtype] = count

    obs_q = (
        select(Floor.location_id, func.count()).select_from(ParkingSlot)
        .join(Zone, Zone.id == ParkingSlot.zone_id)
        .join(Floor, Floor.id == Zone.floor_id)
        .where(ParkingSlot.is_active.is_(True), ParkingSlot.state == SlotState.OBSTRUCTED)
        .group_by(Floor.location_id)
    )
    if scoped_ids is not None:
        obs_q = obs_q.where(Floor.location_id.in_(scoped_ids))
    obs_map = {loc_id: count for loc_id, count in (await db.execute(obs_q)).all()}

    result = []
    for loc in locations:
        occ = occ_map.get(loc.id, {})
        car_occ = occ.get(VehicleType.CAR, 0)
        tw_occ = occ.get(VehicleType.TWO_WHEELER, 0)
        car_total = loc.total_car_slots
        tw_total = loc.total_two_wheeler_slots
        total = car_total + tw_total
        occupied = car_occ + tw_occ
        result.append({
            "location_id": str(loc.id),
            "location_name": loc.name,
            "car_total": car_total,
            "car_occupied": car_occ,
            "car_available": max(0, car_total - car_occ),
            "two_wheeler_total": tw_total,
            "two_wheeler_occupied": tw_occ,
            "two_wheeler_available": max(0, tw_total - tw_occ),
            "obstructions": obs_map.get(loc.id, 0),
            "occupancy_pct": round(occupied / total * 100, 1) if total else 0,
            "availability_pct": round((total - occupied) / total * 100, 1) if total else 100,
        })
    return result


async def _anpr_sessions(db, scoped_ids, area_id, location_id, start, end) -> List[Dict[str, Any]]:
    q = (
        select(AnprSession, Location.name.label("location_name"))
        .outerjoin(Location, Location.id == AnprSession.location_id)
    )
    if area_id:
        q = q.where(Location.area_id == area_id)
    if location_id:
        q = q.where(AnprSession.location_id == location_id)
    elif scoped_ids is not None:
        q = q.where(AnprSession.location_id.in_(scoped_ids))
    if start:
        q = q.where(AnprSession.entry_time >= start)
    if end:
        q = q.where(AnprSession.entry_time <= end)
    q = q.order_by(AnprSession.entry_time.desc()).limit(50000)

    out = []
    for s, location_name in (await db.execute(q)).all():
        out.append({
            "id": str(s.id),
            "location_id": str(s.location_id) if s.location_id else None,
            "city_id": str(s.city_id) if s.city_id else None,
            "number_plate": s.number_plate,
            "vehicle_type": _ev(s.vehicle_type),
            "entry_record_id": str(s.entry_record_id) if s.entry_record_id else None,
            "exit_record_id": str(s.exit_record_id) if s.exit_record_id else None,
            "entry_time": s.entry_time.isoformat() if s.entry_time else None,
            "exit_time": s.exit_time.isoformat() if s.exit_time else None,
            "entry_image_url": s.entry_image_url,
            "exit_image_url": s.exit_image_url,
            "is_active": s.is_active,
            "duration_display": _format_duration(s.entry_time, s.exit_time),
            "location_name": location_name,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })
    return out


# ─────────────────────────────────────────────────────────────
# Peak Occupancy (inlined, self-contained)
# ─────────────────────────────────────────────────────────────
def _accumulate_hourly(hourly, start, end, is_mismatched):
    current = start
    while current < end:
        hour = current.hour
        next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        bucket_end = min(next_hour, end)
        minutes = (bucket_end - current).total_seconds() / 60
        hourly[hour]["vehicle_min"] += minutes
        if is_mismatched:
            hourly[hour]["mismatch_min"] += minutes
        current = bucket_end


def _find_peak_periods(hourly_breakdown, threshold):
    def fmt_hour(h):
        if h in (0, 24):
            return "12:00 AM"
        if h == 12:
            return "12:00 PM"
        return f"{h}:00 AM" if h < 12 else f"{h - 12}:00 PM"

    peaks = []
    i = 0
    while i < 24:
        if hourly_breakdown[i]["occupancy_pct"] >= threshold:
            start_h = i
            occ_sum = mis_sum = count = 0
            while i < 24 and hourly_breakdown[i]["occupancy_pct"] >= threshold:
                occ_sum += hourly_breakdown[i]["occupancy_pct"]
                mis_sum += hourly_breakdown[i]["mismatch_pct"]
                count += 1
                i += 1
            peaks.append({
                "start_hour": start_h,
                "end_hour": i,
                "avg_occupancy_pct": round(occ_sum / count, 1),
                "avg_mismatch_pct": round(mis_sum / count, 1),
                "label": f"{fmt_hour(start_h)} - {fmt_hour(i)}",
            })
        else:
            i += 1
    return peaks


def _generate_insight(zone_name, location_name, floor_label, slot_type, peak_periods, avg_occ, avg_mis):
    type_label = f" {slot_type} slots" if slot_type else ""
    loc = f" - {location_name}" if location_name else ""
    floor = f" ({floor_label})" if floor_label else ""
    if peak_periods:
        top = peak_periods[0]
        base = f"{zone_name}{type_label}{loc}{floor}: {top['avg_occupancy_pct']}% occupied {top['label']}"
        if avg_mis > 5:
            base += f", {avg_mis}% mismatch rate"
        return base
    return f"{zone_name}{type_label}{loc}{floor}: {avg_occ}% avg occupancy"


def _empty_occupancy(threshold, slot_type, start, end):
    return {
        "threshold": threshold, "slot_type_filter": slot_type,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "zones": [], "global_peak_hour": None,
        "global_avg_occupancy_pct": 0, "global_avg_mismatch_pct": 0, "hotspot_zones": [],
    }


async def _compute_occupancy(db, scoped_ids, area_id, location_id, start, end, threshold, slot_type):
    slot_filters = [ParkingSlot.is_active.is_(True)]
    if scoped_ids is not None:
        slot_filters.append(Floor.location_id.in_(scoped_ids))
    if area_id:
        slot_filters.append(Location.area_id == area_id)
    if location_id:
        slot_filters.append(Floor.location_id == location_id)
    if slot_type:
        slot_filters.append(ParkingSlot.slot_type == slot_type)

    event_q = (
        select(
            SlotEvent.parking_slot_id, SlotEvent.new_state, SlotEvent.recorded_at,
            SlotEvent.is_mismatched, ParkingSlot.zone_id,
        )
        .join(ParkingSlot, ParkingSlot.id == SlotEvent.parking_slot_id)
        .outerjoin(Zone, Zone.id == ParkingSlot.zone_id)
        .outerjoin(Floor, Floor.id == Zone.floor_id)
        .outerjoin(Location, Location.id == Floor.location_id)
        .where(SlotEvent.recorded_at >= start, SlotEvent.recorded_at <= end, *slot_filters)
        .order_by(SlotEvent.parking_slot_id, SlotEvent.recorded_at.asc())
    )
    event_rows = (await db.execute(event_q)).all()

    slot_ids_q = (
        select(ParkingSlot.id)
        .outerjoin(Zone, Zone.id == ParkingSlot.zone_id)
        .outerjoin(Floor, Floor.id == Zone.floor_id)
        .outerjoin(Location, Location.id == Floor.location_id)
        .where(*slot_filters)
    )
    scoped_slot_ids = {r[0] for r in (await db.execute(slot_ids_q)).all()}

    initial_states: Dict[uuid.UUID, Tuple] = {}
    if scoped_slot_ids:
        init_q = (
            select(SlotEvent.parking_slot_id, SlotEvent.new_state, SlotEvent.is_mismatched)
            .where(SlotEvent.recorded_at < start, SlotEvent.parking_slot_id.in_(scoped_slot_ids))
            .order_by(SlotEvent.parking_slot_id, SlotEvent.recorded_at.desc())
            .distinct(SlotEvent.parking_slot_id)
        )
        initial_states = {
            r.parking_slot_id: (r.new_state, r.is_mismatched)
            for r in (await db.execute(init_q)).all()
        }

    count_q = (
        select(
            ParkingSlot.zone_id, ParkingSlot.slot_type, func.count().label("cnt"),
            Zone.name.label("zone_name"), Floor.label.label("floor_label"),
            Location.name.label("location_name"), Area.name.label("area_name"),
        )
        .outerjoin(Zone, Zone.id == ParkingSlot.zone_id)
        .outerjoin(Floor, Floor.id == Zone.floor_id)
        .outerjoin(Location, Location.id == Floor.location_id)
        .outerjoin(Area, Area.id == Location.area_id)
        .where(*slot_filters)
        .group_by(
            ParkingSlot.zone_id, ParkingSlot.slot_type,
            Zone.name, Floor.label, Location.name, Area.name,
        )
    )
    zone_meta: Dict[uuid.UUID, Dict[str, Any]] = {}
    for row in (await db.execute(count_q)).all():
        meta = zone_meta.setdefault(row.zone_id, {
            "zone_name": row.zone_name or "Unknown", "floor_label": row.floor_label or "",
            "location_name": row.location_name or "", "area_name": row.area_name,
            "total_slots": 0, "slots_by_type": {},
        })
        meta["total_slots"] += row.cnt
        meta["slots_by_type"][row.slot_type or "GENERAL"] = row.cnt

    if not zone_meta:
        return _empty_occupancy(threshold, slot_type, start, end)

    slot_events_map: Dict[uuid.UUID, List] = defaultdict(list)
    slot_zone_map: Dict[uuid.UUID, uuid.UUID] = {}
    for row in event_rows:
        slot_events_map[row.parking_slot_id].append(row)
        slot_zone_map[row.parking_slot_id] = row.zone_id
    for sid in scoped_slot_ids:
        slot_events_map.setdefault(sid, [])
    missing = scoped_slot_ids - set(slot_zone_map.keys())
    if missing:
        for row in (await db.execute(select(ParkingSlot.id, ParkingSlot.zone_id).where(ParkingSlot.id.in_(missing)))).all():
            slot_zone_map[row.id] = row.zone_id

    num_days = max((end - start).total_seconds() / 86400, 1)
    zone_hourly: Dict[uuid.UUID, Dict[int, Dict[str, float]]] = defaultdict(
        lambda: {h: {"vehicle_min": 0.0, "mismatch_min": 0.0} for h in range(24)}
    )

    for slot_id, events in slot_events_map.items():
        zone_id = slot_zone_map.get(slot_id)
        if zone_id is None or zone_id not in zone_meta:
            continue
        init = initial_states.get(slot_id)
        timeline = [(start, init[0] if init else SlotState.EMPTY, init[1] if init else False)]
        for ev in events:
            timeline.append((ev.recorded_at, ev.new_state, ev.is_mismatched))
        for i in range(len(timeline)):
            interval_start = timeline[i][0]
            interval_end = timeline[i + 1][0] if i + 1 < len(timeline) else end
            state = timeline[i][1]
            if interval_start >= interval_end:
                continue
            if state in (SlotState.VEHICLE, SlotState.OBSTRUCTED):
                _accumulate_hourly(zone_hourly[zone_id], interval_start, interval_end, timeline[i][2])

    zones_result = []
    all_by_hour = {h: {"vehicle_min": 0.0, "total_possible": 0.0} for h in range(24)}
    for zone_id, meta in zone_meta.items():
        total_slots = meta["total_slots"]
        hourly_data = zone_hourly[zone_id]
        possible_per_hour = total_slots * num_days * 60

        hourly_breakdown = []
        for h in range(24):
            veh = hourly_data[h]["vehicle_min"]
            mis = hourly_data[h]["mismatch_min"]
            occ_pct = round(min(veh / possible_per_hour * 100, 100), 1) if possible_per_hour > 0 else 0
            mis_pct = round(mis / veh * 100, 1) if veh > 0 else 0
            occupied = round(veh / (num_days * 60)) if num_days > 0 else 0
            hourly_breakdown.append({
                "hour": h, "occupancy_pct": occ_pct,
                "occupied_slots": min(occupied, total_slots),
                "total_slots": total_slots, "mismatch_pct": mis_pct,
            })
            all_by_hour[h]["vehicle_min"] += veh
            all_by_hour[h]["total_possible"] += possible_per_hour

        peak_periods = _find_peak_periods(hourly_breakdown, threshold)
        total_veh = sum(hourly_data[h]["vehicle_min"] for h in range(24))
        total_mis = sum(hourly_data[h]["mismatch_min"] for h in range(24))
        total_possible = possible_per_hour * 24
        avg_occ = round(min(total_veh / total_possible * 100, 100), 1) if total_possible > 0 else 0
        avg_mis = round(total_mis / total_veh * 100, 1) if total_veh > 0 else 0
        zones_result.append({
            "zone_id": str(zone_id), "zone_name": meta["zone_name"],
            "floor_label": meta["floor_label"], "location_name": meta["location_name"],
            "area_name": meta["area_name"], "total_slots": total_slots,
            "slots_by_type": meta["slots_by_type"], "avg_occupancy_pct": avg_occ,
            "avg_mismatch_pct": avg_mis, "hourly_breakdown": hourly_breakdown,
            "peak_periods": peak_periods,
            "insight": _generate_insight(meta["zone_name"], meta["location_name"], meta["floor_label"], slot_type, peak_periods, avg_occ, avg_mis),
        })

    zones_result.sort(key=lambda z: z["avg_occupancy_pct"], reverse=True)

    global_peak_hour, max_occ = None, 0
    g_veh = g_poss = g_mis = 0
    for h in range(24):
        veh = all_by_hour[h]["vehicle_min"]
        poss = all_by_hour[h]["total_possible"]
        g_veh += veh
        g_poss += poss
        if poss > 0 and veh / poss > max_occ:
            max_occ = veh / poss
            global_peak_hour = h
    for zid in zone_hourly:
        for h in range(24):
            g_mis += zone_hourly[zid][h]["mismatch_min"]

    return {
        "threshold": threshold, "slot_type_filter": slot_type,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "zones": zones_result,
        "global_peak_hour": global_peak_hour,
        "global_avg_occupancy_pct": round(min(g_veh / g_poss * 100, 100), 1) if g_poss > 0 else 0,
        "global_avg_mismatch_pct": round(g_mis / g_veh * 100, 1) if g_veh > 0 else 0,
        "hotspot_zones": [z["zone_name"] for z in zones_result if z["avg_occupancy_pct"] >= threshold],
    }


# ─────────────────────────────────────────────────────────────
# Data endpoints
# ─────────────────────────────────────────────────────────────
@router.get("/summary")
async def get_report_summary(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    camera_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """AI Parking + Overview summary (matches the frontend ReportData shape)."""
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped = await _resolve_scope(db, area_id, user_location_ids)
    payload = await _report_payload(
        db, scoped, area_id, location_id, camera_id, status, event_type,
        _parse_date(start_date), _parse_date(end_date),
    )
    payload.pop("_raw_sessions", None)
    return payload


@router.get("/occupancy-analysis")
async def get_occupancy_analysis(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    start_date: str = Query(..., description="ISO datetime"),
    end_date: str = Query(..., description="ISO datetime"),
    threshold: int = Query(80, ge=1, le=100),
    slot_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Peak occupancy heatmap per zone."""
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped = await _resolve_scope(db, area_id, user_location_ids)
    return await _compute_occupancy(
        db, scoped, area_id, location_id,
        datetime.fromisoformat(start_date), datetime.fromisoformat(end_date),
        threshold, slot_type.upper() if slot_type else None,
    )


@router.get("/anpr-summary")
async def get_anpr_summary(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """ANPR live occupancy summary for the report page."""
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped = await _resolve_scope(db, area_id, user_location_ids)
    return await _anpr_summary(db, scoped, location_id)


@router.get("/anpr-locations")
async def get_anpr_locations(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """ANPR per-location occupancy for the report page."""
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped = await _resolve_scope(db, area_id, user_location_ids)
    return {"locations": await _anpr_locations(db, scoped, area_id, location_id)}


@router.get("/anpr-sessions")
async def get_anpr_sessions(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """ANPR session log for the report page."""
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped = await _resolve_scope(db, area_id, user_location_ids)
    items = await _anpr_sessions(db, scoped, area_id, location_id, _parse_date(start_date), _parse_date(end_date))
    return {"items": items, "total": len(items)}


# ─────────────────────────────────────────────────────────────
# Unified export — ALL sections in one file
# ─────────────────────────────────────────────────────────────
def _status_label(s: Dict[str, Any]) -> str:
    is_obs = s["event_type"] == SlotState.OBSTRUCTED
    if s["is_active"]:
        return "Blocked" if is_obs else "Parked"
    return "Cleared" if is_obs else "Completed"


async def _gather_export_sections(
    db, scoped, area_id, location_id, camera_id, status, event_type, start, end, threshold, slot_type,
) -> List[Tuple[str, List[str], List[List]]]:
    """Build (title, headers, rows) blocks for every report section."""
    payload = await _report_payload(db, scoped, area_id, location_id, camera_id, status, event_type, start, end)
    summary = payload["summary"]
    sessions = payload["_raw_sessions"]
    anpr_summary = await _anpr_summary(db, scoped, location_id)
    anpr_locs = await _anpr_locations(db, scoped, area_id, location_id)
    anpr_sessions = await _anpr_sessions(db, scoped, area_id, location_id, start, end)

    sections: List[Tuple[str, List[str], List[List]]] = []

    # Summary (key/value)
    sc = payload["slot_counts"]
    dev = payload["device_summary"]
    al = payload["alert_summary"]
    summary_rows = [
        ["Total Sessions", summary["total_sessions"]],
        ["Active Sessions", summary["active_sessions"]],
        ["Completed Sessions", summary["completed_sessions"]],
        ["Vehicle Sessions", summary["vehicle_sessions"]],
        ["Obstructed Sessions", summary["obstructed_sessions"]],
        ["Car Sessions", summary["car_sessions"]],
        ["Two-Wheeler Sessions", summary["two_wheeler_sessions"]],
        ["Avg Duration (min)", summary["avg_duration_minutes"] if summary["avg_duration_minutes"] is not None else ""],
        ["Peak Hour", summary["peak_hour"] if summary["peak_hour"] is not None else ""],
        ["Unique Slots", summary["unique_slots"]],
        ["Slots — Total", sc["total"]],
        ["Slots — Available", sc["available"]],
        ["Slots — Occupied", sc["occupied"]],
        ["Slots — Obstructed", sc["obstructed"]],
        ["Devices — Total/Online/Offline", f"{dev['total']}/{dev['online']}/{dev['offline']}"],
        ["Alerts — Total/Active/Resolved", f"{al['total']}/{al['active']}/{al['resolved']}"],
    ]
    sections.append(("Summary", ["Metric", "Value"], summary_rows))

    # Parking sessions
    p_headers = ["Slot", "Type", "Vehicle", "Area", "Location", "Camera", "Entry", "Exit", "Duration (min)", "Status"]
    p_rows = [[
        s["slot_label"] or "",
        "Obstructed" if s["event_type"] == SlotState.OBSTRUCTED else "Vehicle",
        s.get("detected_vehicle_type") or "",
        s["area_name"] or "", s["location_name"] or "", s["camera_label"] or "",
        _fmt_dt(s["entry_time"]), _fmt_dt(s["exit_time"]),
        s["duration_minutes"] if s["duration_minutes"] is not None else "",
        _status_label(s),
    ] for s in sessions]
    sections.append(("Parking Sessions", p_headers, p_rows))

    # ANPR summary (incl. per-location)
    a_headers = ["Location", "Car Occ", "Car Total", "2W Occ", "2W Total", "Obstructions", "Occupancy %", "Availability %"]
    a_rows = [[
        "ALL (live)", anpr_summary["car_occupied"], anpr_summary["car_total"],
        anpr_summary["two_wheeler_occupied"], anpr_summary["two_wheeler_total"],
        anpr_summary["obstructions"], "", "",
    ]]
    for l in anpr_locs:
        a_rows.append([
            l["location_name"], l["car_occupied"], l["car_total"],
            l["two_wheeler_occupied"], l["two_wheeler_total"],
            l["obstructions"], l["occupancy_pct"], l["availability_pct"],
        ])
    sections.append(("ANPR Summary", a_headers, a_rows))

    # ANPR sessions
    as_headers = ["Number Plate", "Type", "Location", "Entry", "Exit", "Duration", "Status"]
    as_rows = [[
        s["number_plate"], s["vehicle_type"], s["location_name"] or "",
        _fmt_dt(datetime.fromisoformat(s["entry_time"])) if s["entry_time"] else "",
        _fmt_dt(datetime.fromisoformat(s["exit_time"])) if s["exit_time"] else "",
        s["duration_display"] or "Active",
        "Inside" if s["is_active"] else "Exited",
    ] for s in anpr_sessions]
    sections.append(("ANPR Sessions", as_headers, as_rows))

    # Occupancy heatmap
    if start and end:
        occ = await _compute_occupancy(db, scoped, area_id, location_id, start, end, threshold, slot_type)
        o_headers = ["Zone", "Floor", "Location", "Area", "Total Slots", "Avg Occ %", "Avg Mismatch %"] + [f"H{h}" for h in range(24)] + ["Peak Periods", "Insight"]
        o_rows = []
        for z in occ["zones"]:
            row = [z["zone_name"], z["floor_label"], z["location_name"], z["area_name"] or "",
                   z["total_slots"], z["avg_occupancy_pct"], z["avg_mismatch_pct"]]
            row += [hb["occupancy_pct"] for hb in z["hourly_breakdown"]]
            row += ["; ".join(p["label"] for p in z["peak_periods"]), z["insight"]]
            o_rows.append(row)
        sections.append(("Occupancy", o_headers, o_rows))

    return sections


@router.get("/export-excel")
async def export_all_excel(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    camera_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    threshold: int = Query(80, ge=1, le=100),
    slot_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Combined multi-sheet Excel — one sheet per section."""
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped = await _resolve_scope(db, area_id, user_location_ids)
    sections = await _gather_export_sections(
        db, scoped, area_id, location_id, camera_id, status, event_type,
        _parse_date(start_date), _parse_date(end_date), threshold,
        slot_type.upper() if slot_type else None,
    )
    output = generate_excel_multi([(t, h, r) for t, h, r in sections])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=reports_{ts}.xlsx"},
    )


@router.get("/export-pdf")
async def export_all_pdf(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    camera_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    threshold: int = Query(80, ge=1, le=100),
    slot_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Dashboard-styled PDF mirroring the Reports page (cards, charts, heatmap)."""
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped = await _resolve_scope(db, area_id, user_location_ids)
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    st = slot_type.upper() if slot_type else None

    payload = await _report_payload(db, scoped, area_id, location_id, camera_id, status, event_type, start, end)
    summary = payload["summary"]
    raw_sessions = payload["_raw_sessions"]
    sc = payload["slot_counts"]
    dev = payload["device_summary"]
    al = payload["alert_summary"]
    anpr_sum = await _anpr_summary(db, scoped, location_id)
    anpr_locs = await _anpr_locations(db, scoped, area_id, location_id)
    anpr_sess = await _anpr_sessions(db, scoped, area_id, location_id, start, end)
    an = _anpr_analytics(anpr_sess)
    occ = await _compute_occupancy(db, scoped, area_id, location_id, start, end, threshold, st) if (start and end) else None

    range_label = f"{start.date().isoformat()} to {end.date().isoformat()}" if (start and end) else "All time"

    parking_rows = [[
        s["slot_label"] or "",
        "Obstructed" if s["event_type"] == SlotState.OBSTRUCTED else "Vehicle",
        s.get("detected_vehicle_type") or "-",
        s["area_name"] or "-", s["location_name"] or "-", s["camera_label"] or "-",
        _fmt_dt(s["entry_time"]), _fmt_dt(s["exit_time"]),
        s["duration_minutes"] if s["duration_minutes"] is not None else "",
        _status_label(s),
    ] for s in raw_sessions]

    anpr_rows = [[
        s["number_plate"], "Car" if s["vehicle_type"] == "CAR" else "2-Wheeler", s["location_name"] or "-",
        _fmt_dt(datetime.fromisoformat(s["entry_time"])) if s["entry_time"] else "",
        _fmt_dt(datetime.fromisoformat(s["exit_time"])) if s["exit_time"] else "",
        s["duration_display"] or "Active",
        "Inside" if (s["is_active"] or not s["exit_time"]) else "Exited",
    ] for s in anpr_sess]

    loc_rows = [[
        l["location_name"], l["car_occupied"], l["car_total"],
        l["two_wheeler_occupied"], l["two_wheeler_total"],
        f"{l['occupancy_pct']}%", f"{l['availability_pct']}%",
    ] for l in anpr_locs]

    data = {
        "kpis": [
            ("Parking Sessions", summary["total_sessions"], f"{summary['active_sessions']} active", "teal"),
            ("Slots Available", sc["available"], f"of {sc['total']}", "blue"),
            ("ANPR Entries", an["entries"], f"{an['exits']} exits", "violet"),
            ("Vehicles Inside", an["inside"], "ANPR live", "indigo"),
            ("Avg Park Time", _fmt_minutes(summary["avg_duration_minutes"]), "per session", "amber"),
            ("Obstructions", summary["obstructed_sessions"], "parking events", "orange"),
            ("Active Alerts", al["active"], f"{al['total']} total", "red"),
        ],
        "slot_counts": sc,
        "anpr_summary": anpr_sum,
        "highlights": [
            ("Peak Parking Hour", _fmt_hour(summary["peak_hour"])),
            ("Peak ANPR Hour", _fmt_hour(an["peak_hour"])),
            ("Unique Plates", an["unique_plates"]),
            ("Devices Online", f"{dev['online']}/{dev['total']}"),
        ],
        "parking": {
            "stats": [
                ("Total Sessions", summary["total_sessions"], "", "teal"),
                ("Currently Parked", summary["active_sessions"], "", "red"),
                ("Avg Duration", _fmt_minutes(summary["avg_duration_minutes"]), "", "violet"),
                ("Peak Hour", _fmt_hour(summary["peak_hour"]), "", "amber"),
                ("Vehicles", summary["vehicle_sessions"], "", "blue"),
                ("Obstructed", summary["obstructed_sessions"], "", "orange"),
            ],
            "hourly": summary["hourly_distribution"],
            "duration": summary["duration_distribution"],
            "top_slots": summary["top_slots"],
            "device": dev,
            "alert": al,
            "sessions": parking_rows,
        },
        "anpr": {
            "kpis": [
                ("Entries", an["entries"], "", "violet"),
                ("Exits", an["exits"], "", "blue"),
                ("Inside Now", an["inside"], "", "indigo"),
                ("Unique Plates", an["unique_plates"], "", "teal"),
                ("Cars", an["cars"], "", "blue"),
                ("2-Wheelers", an["two_wheelers"], "", "indigo"),
                ("Avg Duration", _fmt_minutes(an["avg_dur"]), "", "amber"),
                ("Longest", _fmt_minutes(an["max_dur"]), "", "orange"),
            ],
            "cars": an["cars"], "two_wheelers": an["two_wheelers"],
            "hourly": an["hourly"], "top_plates": an["top_plates"], "top_locations": an["top_locations"],
            "locations": loc_rows, "sessions": anpr_rows,
        },
        "occupancy": {
            "stats": [
                ("Avg Occupancy", f"{occ['global_avg_occupancy_pct']}%" if occ else "-", "", "teal"),
                ("Hotspot Zones", len(occ["hotspot_zones"]) if occ else 0, f"above {threshold}%", "red"),
                ("Peak Hour", _fmt_hour(occ["global_peak_hour"]) if occ else "-", "", "amber"),
                ("Mismatch Rate", f"{occ['global_avg_mismatch_pct']}%" if occ else "-", "", "orange"),
            ],
            "zones": occ["zones"] if occ else [],
            "threshold": threshold,
            "insights": [z["insight"] for z in (occ["zones"] if occ else []) if z["peak_periods"]],
        },
    }

    output = generate_report_pdf("AI Parking & ANPR - Analytics Report", range_label, data)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=reports_{ts}.pdf"},
    )


@router.get("/export-csv")
async def export_all_csv(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    camera_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    threshold: int = Query(80, ge=1, le=100),
    slot_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_EXPORT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Combined CSV — labeled section blocks in one file."""
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)
    scoped = await _resolve_scope(db, area_id, user_location_ids)
    sections = await _gather_export_sections(
        db, scoped, area_id, location_id, camera_id, status, event_type,
        _parse_date(start_date), _parse_date(end_date), threshold,
        slot_type.upper() if slot_type else None,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    for title, headers, rows in sections:
        writer.writerow([f"=== {title.upper()} ==="])
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
        writer.writerow([])
    output.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=reports_{ts}.csv"},
    )
