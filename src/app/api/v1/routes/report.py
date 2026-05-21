import uuid
import csv
import io
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, verify_location_in_scope
from src.app.core.constants import Permission, SlotState, DeviceStatus, AlertSeverity, AlertStatus
from src.app.db.session import get_db
from src.app.models.slot_event import SlotEvent
from src.app.models.parking_slot import ParkingSlot
from src.app.models.camera import Camera
from src.app.models.zone import Zone
from src.app.models.floor import Floor
from src.app.models.location import Location
from src.app.models.area import Area
from src.app.models.city import City
from src.app.models.device import Device
from src.app.models.alert_event import AlertEvent

router = APIRouter(prefix="/reports", tags=["Reports"])


async def _build_sessions(
    db: AsyncSession,
    location_ids: Optional[Set[uuid.UUID]],
    area_id: Optional[uuid.UUID],
    location_id: Optional[uuid.UUID],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
) -> List[Dict[str, Any]]:
    """Build parking sessions using LEAD() — reuses the same logic as slot_event service."""
    filters = [ParkingSlot.is_active == True]
    if location_ids is not None:
        filters.append(Floor.location_id.in_(location_ids))
    if area_id:
        filters.append(Location.area_id == area_id)
    if location_id:
        filters.append(Floor.location_id == location_id)
    if start_time:
        filters.append(SlotEvent.recorded_at >= start_time)
    if end_time:
        filters.append(SlotEvent.recorded_at <= end_time)

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
            SlotEvent.id.label("entry_event_id"),
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

    sessions = []
    for row in rows:
        entry_time = row.entry_time
        exit_time = row.exit_time if row.next_prev_state == row.new_state else None
        duration_minutes = None
        if exit_time:
            duration_minutes = round((exit_time - entry_time).total_seconds() / 60, 1)

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
            "duration_minutes": duration_minutes,
            "is_active": exit_time is None,
            "hour": entry_time.hour,
        })

    return sessions


def _compute_summary(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute all summary stats from sessions list."""
    if not sessions:
        return {
            "total_sessions": 0, "active_sessions": 0, "completed_sessions": 0,
            "vehicle_sessions": 0, "obstructed_sessions": 0,
            "car_sessions": 0, "two_wheeler_sessions": 0,
            "avg_duration_minutes": None, "max_duration_minutes": None, "min_duration_minutes": None,
            "peak_hour": None, "peak_hour_count": 0,
            "hourly_distribution": [0] * 24,
            "duration_distribution": {"under_30m": 0, "30m_to_1h": 0, "1h_to_2h": 0, "2h_to_8h": 0, "over_8h": 0},
            "top_slots": [],
            "unique_slots": 0,
        }

    total = len(sessions)
    active = sum(1 for s in sessions if s["is_active"])
    completed = total - active
    vehicles = sum(1 for s in sessions if s["event_type"] == SlotState.VEHICLE)
    obstructed = total - vehicles
    car_sessions = sum(1 for s in sessions if s.get("detected_vehicle_type") == "CAR")
    two_wheeler_sessions = sum(1 for s in sessions if s.get("detected_vehicle_type") == "TWO_WHEELER")

    # Duration stats (completed only)
    durations = [s["duration_minutes"] for s in sessions if s["duration_minutes"] is not None]
    avg_dur = round(sum(durations) / len(durations), 1) if durations else None
    max_dur = round(max(durations), 1) if durations else None
    min_dur = round(min(durations), 1) if durations else None

    # Hourly distribution
    hourly = [0] * 24
    for s in sessions:
        hourly[s["hour"]] += 1
    peak_hour = hourly.index(max(hourly)) if max(hourly) > 0 else None
    peak_count = max(hourly)

    # Duration distribution
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

    # Top slots
    slot_counts = Counter(s["slot_label"] for s in sessions)
    top_slots = [{"label": label, "count": count} for label, count in slot_counts.most_common(10)]

    # Unique slots
    unique_slots = len(slot_counts)

    return {
        "total_sessions": total,
        "active_sessions": active,
        "completed_sessions": completed,
        "vehicle_sessions": vehicles,
        "obstructed_sessions": obstructed,
        "car_sessions": car_sessions,
        "two_wheeler_sessions": two_wheeler_sessions,
        "avg_duration_minutes": avg_dur,
        "max_duration_minutes": max_dur,
        "min_duration_minutes": min_dur,
        "peak_hour": peak_hour,
        "peak_hour_count": peak_count,
        "hourly_distribution": hourly,
        "duration_distribution": dur_dist,
        "top_slots": top_slots,
        "unique_slots": unique_slots,
    }


@router.get("/summary")
async def get_report_summary(
    area_id: uuid.UUID = Query(None),
    location_id: uuid.UUID = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Comprehensive report summary with stats, distributions, and session list."""
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None

    if location_id:
        verify_location_in_scope(location_id, user_location_ids)

    # Narrow scope by area
    scoped_ids = user_location_ids
    if area_id:
        result = await db.execute(select(Location.id).where(Location.area_id == area_id))
        area_loc_ids = {row[0] for row in result.all()}
        scoped_ids = (scoped_ids & area_loc_ids) if scoped_ids is not None else area_loc_ids

    # Build sessions
    sessions = await _build_sessions(db, scoped_ids, area_id, location_id, start, end)
    summary = _compute_summary(sessions)

    # Device summary (scoped)
    dev_q = select(
        Device.status, func.count()
    ).where(Device.is_active == True).group_by(Device.status)
    if scoped_ids is not None:
        dev_q = dev_q.where(Device.location_id.in_(scoped_ids))
    elif location_id:
        dev_q = dev_q.where(Device.location_id == location_id)
    dev_rows = (await db.execute(dev_q)).all()
    device_summary = {"total": 0, "online": 0, "offline": 0}
    for status, count in dev_rows:
        device_summary["total"] += count
        if status == DeviceStatus.ONLINE:
            device_summary["online"] = count
        else:
            device_summary["offline"] += count

    # Alert summary (scoped)
    alert_q = select(
        AlertEvent.severity, AlertEvent.status, func.count()
    ).group_by(AlertEvent.severity, AlertEvent.status)
    if scoped_ids is not None:
        alert_q = alert_q.where(AlertEvent.location_id.in_(scoped_ids))
    elif location_id:
        alert_q = alert_q.where(AlertEvent.location_id == location_id)
    if start:
        alert_q = alert_q.where(AlertEvent.created_at >= start)
    if end:
        alert_q = alert_q.where(AlertEvent.created_at <= end)
    alert_rows = (await db.execute(alert_q)).all()
    alert_summary = {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0, "active": 0, "resolved": 0}
    for severity, status, count in alert_rows:
        alert_summary["total"] += count
        if severity == AlertSeverity.CRITICAL:
            alert_summary["critical"] += count
        elif severity == AlertSeverity.HIGH:
            alert_summary["high"] += count
        elif severity == AlertSeverity.MEDIUM:
            alert_summary["medium"] += count
        else:
            alert_summary["low"] += count
        if status == AlertStatus.ACTIVE:
            alert_summary["active"] += count
        elif status == AlertStatus.RESOLVED:
            alert_summary["resolved"] += count

    # Format sessions for response (limit to 500 for display, full data in CSV)
    formatted_sessions = []
    for s in sessions[:500]:
        formatted_sessions.append({
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
        })

    return {
        "summary": summary,
        "device_summary": device_summary,
        "alert_summary": alert_summary,
        "sessions": formatted_sessions,
        "total_sessions_in_period": len(sessions),
    }


@router.get("/export-csv")
async def export_report_csv(
    area_id: uuid.UUID = Query(None),
    location_id: uuid.UUID = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.REPORTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Export full report data as CSV."""
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None

    if location_id:
        verify_location_in_scope(location_id, user_location_ids)

    scoped_ids = user_location_ids
    if area_id:
        result = await db.execute(select(Location.id).where(Location.area_id == area_id))
        area_loc_ids = {row[0] for row in result.all()}
        scoped_ids = (scoped_ids & area_loc_ids) if scoped_ids is not None else area_loc_ids

    sessions = await _build_sessions(db, scoped_ids, area_id, location_id, start, end)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Slot", "Camera", "Location", "Area", "City", "Type", "Vehicle Type", "Entry Time", "Exit Time", "Duration (min)", "Status"])
    for s in sessions:
        is_obs = s["event_type"] == SlotState.OBSTRUCTED
        status = ("Blocked" if is_obs else "Parked") if s["is_active"] else ("Cleared" if is_obs else "Completed")
        writer.writerow([
            s["slot_label"] or "",
            s["camera_label"] or "",
            s["location_name"] or "",
            s["area_name"] or "",
            s["city_name"] or "",
            "Obstructed" if is_obs else "Vehicle",
            s.get("detected_vehicle_type") or "",
            s["entry_time"].isoformat() if s["entry_time"] else "",
            s["exit_time"].isoformat() if s["exit_time"] else "",
            s["duration_minutes"] or "",
            status,
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=parking_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"},
    )
