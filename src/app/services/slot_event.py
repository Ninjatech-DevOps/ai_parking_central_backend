import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import groupby
from operator import attrgetter
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import SlotState
from src.app.models.slot_event import SlotEvent
from src.app.models.parking_slot import ParkingSlot
from src.app.models.camera import Camera
from src.app.models.zone import Zone
from src.app.models.floor import Floor
from src.app.models.location import Location
from src.app.models.area import Area
from src.app.models.city import City
from src.app.repositories.slot_event import SlotEventRepository


class SlotEventService:
    def __init__(self, repo: SlotEventRepository, db: AsyncSession):
        self.repo = repo
        self.db = db

    async def get_events_by_slot(
        self,
        slot_id: uuid.UUID,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SlotEvent]:
        return await self.repo.get_by_slot_id(slot_id, start_time, end_time, limit)

    async def get_parking_sessions(
        self,
        location_ids: Optional[Set[uuid.UUID]] = None,
        area_id: Optional[uuid.UUID] = None,
        location_id: Optional[uuid.UUID] = None,
        camera_id: Optional[uuid.UUID] = None,
        slot_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Build parking sessions using LEAD() window function — single query, no N+1.

        For each slot, LEAD() looks ahead to find the next event's recorded_at
        and new_state. If the current event is new_state=VEHICLE and the next
        event has previous_state=VEHICLE, the next event's time is the exit.
        """
        # Build base filters for the where clause
        filters = [ParkingSlot.is_active == True]
        if location_ids is not None:
            filters.append(Floor.location_id.in_(location_ids))
        if area_id:
            filters.append(Location.area_id == area_id)
        if location_id:
            filters.append(Floor.location_id == location_id)
        if camera_id:
            filters.append(ParkingSlot.camera_id == camera_id)
        if slot_id:
            filters.append(SlotEvent.parking_slot_id == slot_id)
        if start_time:
            filters.append(SlotEvent.recorded_at >= start_time)
        if end_time:
            filters.append(SlotEvent.recorded_at <= end_time)

        # CTE: all events with LEAD() to peek at next event per slot
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
                SlotEvent.image_url,
                SlotEvent.recorded_at.label("entry_time"),
                next_time,
                next_prev_state,
                ParkingSlot.label.label("slot_label"),
                Camera.position_label.label("camera_label"),
                Camera.id.label("cam_id"),
                Location.name.label("location_name"),
                Location.id.label("loc_id"),
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

        # Filter by event type (default: VEHICLE only, or OBSTRUCTED, or both)
        if event_type and event_type.upper() in (SlotState.VEHICLE, SlotState.OBSTRUCTED):
            session_q = select(events_cte).where(events_cte.c.new_state == event_type.upper())
        else:
            session_q = select(events_cte).where(
                events_cte.c.new_state.in_([SlotState.VEHICLE, SlotState.OBSTRUCTED])
            )

        # Filter by status: parked (active) vs completed
        if status == "parked":
            # Active: no exit yet (exit_time is NULL or next event's prev_state doesn't match)
            session_q = session_q.where(
                (events_cte.c.exit_time.is_(None)) | (events_cte.c.next_prev_state != events_cte.c.new_state)
            )
        elif status == "completed":
            # Completed: exit exists (next event's prev_state matches current new_state)
            session_q = session_q.where(
                events_cte.c.exit_time.isnot(None) & (events_cte.c.next_prev_state == events_cte.c.new_state)
            )

        # Filter by duration (only applies to completed sessions with valid exit_time)
        if min_duration is not None or max_duration is not None:
            duration_expr = func.extract(
                "epoch", events_cte.c.exit_time - events_cte.c.entry_time
            ) / 60.0
            # Only include completed sessions (has valid exit)
            session_q = session_q.where(
                events_cte.c.exit_time.isnot(None) & (events_cte.c.next_prev_state == events_cte.c.new_state)
            )
            if min_duration is not None:
                session_q = session_q.where(duration_expr >= min_duration)
            if max_duration is not None:
                session_q = session_q.where(duration_expr <= max_duration)

        # Count total
        count_q = select(func.count()).select_from(session_q.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        # Fetch paginated
        session_q = session_q.order_by(events_cte.c.entry_time.desc()).offset(skip).limit(limit)
        rows = (await self.db.execute(session_q)).all()

        sessions = []
        for row in rows:
            entry_time = row.entry_time
            # exit_time is valid only if next event's previous_state matches the entry state
            exit_time = row.exit_time if row.next_prev_state == row.new_state else None
            duration_minutes = None
            if exit_time:
                duration_minutes = round(
                    (exit_time - entry_time).total_seconds() / 60, 1
                )

            sessions.append({
                "entry_event_id": str(row.entry_event_id),
                "slot_id": str(row.parking_slot_id),
                "slot_label": row.slot_label,
                "camera_label": row.camera_label,
                "location_name": row.location_name,
                "location_id": str(row.loc_id) if row.loc_id else None,
                "area_name": row.area_name,
                "city_name": row.city_name,
                "camera_id": str(row.cam_id) if row.cam_id else None,
                "event_type": row.new_state,
                "detected_vehicle_type": row.detected_vehicle_type,
                "entry_time": entry_time.isoformat(),
                "exit_time": exit_time.isoformat() if exit_time else None,
                "duration_minutes": duration_minutes,
                "image_url": row.image_url,
                "is_active": exit_time is None,
            })

        return sessions, total

    async def compute_occupancy_analysis(
        self,
        location_ids: Optional[Set[uuid.UUID]],
        area_id: Optional[uuid.UUID],
        location_id: Optional[uuid.UUID],
        start_time: datetime,
        end_time: datetime,
        threshold: int = 80,
        slot_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compute per-zone hourly occupancy analysis with mismatch tracking.

        Reconstructs per-slot state timelines from slot_events, splits VEHICLE
        intervals into hour-of-day buckets, aggregates by zone, and identifies
        peak periods above the threshold.
        """
        # --- Build scope filters for slot queries ---
        slot_filters = [ParkingSlot.is_active.is_(True)]
        if location_ids is not None:
            slot_filters.append(Floor.location_id.in_(location_ids))
        if area_id:
            slot_filters.append(Location.area_id == area_id)
        if location_id:
            slot_filters.append(Floor.location_id == location_id)
        if slot_type:
            slot_filters.append(ParkingSlot.slot_type == slot_type)

        # --- Query 1: Events in range ---
        event_q = (
            select(
                SlotEvent.parking_slot_id,
                SlotEvent.new_state,
                SlotEvent.recorded_at,
                SlotEvent.is_mismatched,
                ParkingSlot.zone_id,
                ParkingSlot.slot_type.label("slot_type"),
                Zone.name.label("zone_name"),
                Floor.label.label("floor_label"),
                Location.name.label("location_name"),
                Area.name.label("area_name"),
            )
            .join(ParkingSlot, ParkingSlot.id == SlotEvent.parking_slot_id)
            .outerjoin(Zone, Zone.id == ParkingSlot.zone_id)
            .outerjoin(Floor, Floor.id == Zone.floor_id)
            .outerjoin(Location, Location.id == Floor.location_id)
            .outerjoin(Area, Area.id == Location.area_id)
            .where(
                SlotEvent.recorded_at >= start_time,
                SlotEvent.recorded_at <= end_time,
                *slot_filters,
            )
            .order_by(SlotEvent.parking_slot_id, SlotEvent.recorded_at.asc())
        )
        event_rows = (await self.db.execute(event_q)).all()

        # --- Query 2: Initial state per slot (last event before start) ---
        # Get the slot IDs that appear in our scope
        slot_ids_q = (
            select(ParkingSlot.id)
            .outerjoin(Zone, Zone.id == ParkingSlot.zone_id)
            .outerjoin(Floor, Floor.id == Zone.floor_id)
            .outerjoin(Location, Location.id == Floor.location_id)
            .outerjoin(Area, Area.id == Location.area_id)
            .where(*slot_filters)
        )
        scoped_slot_ids = {row[0] for row in (await self.db.execute(slot_ids_q)).all()}

        initial_state_q = (
            select(
                SlotEvent.parking_slot_id,
                SlotEvent.new_state,
                SlotEvent.is_mismatched,
            )
            .where(
                SlotEvent.recorded_at < start_time,
                SlotEvent.parking_slot_id.in_(scoped_slot_ids) if scoped_slot_ids else False,
            )
            .order_by(SlotEvent.parking_slot_id, SlotEvent.recorded_at.desc())
            .distinct(SlotEvent.parking_slot_id)
        )
        initial_rows = (await self.db.execute(initial_state_q)).all() if scoped_slot_ids else []
        initial_states = {
            row.parking_slot_id: (row.new_state, row.is_mismatched)
            for row in initial_rows
        }

        # --- Query 3: Slot counts per zone grouped by slot_type ---
        slot_count_q = (
            select(
                ParkingSlot.zone_id,
                ParkingSlot.slot_type,
                func.count().label("cnt"),
                Zone.name.label("zone_name"),
                Floor.label.label("floor_label"),
                Location.name.label("location_name"),
                Area.name.label("area_name"),
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
        slot_count_rows = (await self.db.execute(slot_count_q)).all()

        # Build zone metadata
        zone_meta: Dict[uuid.UUID, Dict[str, Any]] = {}
        for row in slot_count_rows:
            if row.zone_id not in zone_meta:
                zone_meta[row.zone_id] = {
                    "zone_name": row.zone_name or "Unknown",
                    "floor_label": row.floor_label or "",
                    "location_name": row.location_name or "",
                    "area_name": row.area_name,
                    "total_slots": 0,
                    "slots_by_type": {},
                }
            zone_meta[row.zone_id]["total_slots"] += row.cnt
            zone_meta[row.zone_id]["slots_by_type"][row.slot_type or "GENERAL"] = row.cnt

        if not zone_meta:
            return self._empty_occupancy_response(threshold, slot_type, start_time, end_time)

        # --- Build per-slot event lists (merge initial state + in-range events) ---
        # Group event_rows by parking_slot_id
        slot_events_map: Dict[uuid.UUID, List] = defaultdict(list)
        slot_zone_map: Dict[uuid.UUID, uuid.UUID] = {}
        for row in event_rows:
            slot_events_map[row.parking_slot_id].append(row)
            slot_zone_map[row.parking_slot_id] = row.zone_id

        # Also include slots with no events in range (they maintain initial state)
        for sid in scoped_slot_ids:
            if sid not in slot_events_map:
                slot_events_map[sid] = []

        # We need zone_id for slots with no events — query it
        if scoped_slot_ids - set(slot_zone_map.keys()):
            missing_ids = scoped_slot_ids - set(slot_zone_map.keys())
            zone_q = (
                select(ParkingSlot.id, ParkingSlot.zone_id)
                .where(ParkingSlot.id.in_(missing_ids))
            )
            for row in (await self.db.execute(zone_q)).all():
                slot_zone_map[row.id] = row.zone_id

        # --- Compute hourly buckets per zone ---
        num_days = max((end_time - start_time).total_seconds() / 86400, 1)
        # zone_id -> hour -> {vehicle_min, mismatch_min}
        zone_hourly: Dict[uuid.UUID, Dict[int, Dict[str, float]]] = defaultdict(
            lambda: {h: {"vehicle_min": 0.0, "mismatch_min": 0.0} for h in range(24)}
        )

        for slot_id, events in slot_events_map.items():
            zone_id = slot_zone_map.get(slot_id)
            if zone_id is None or zone_id not in zone_meta:
                continue

            # Build timeline: list of (timestamp, state, is_mismatched)
            timeline = []
            init = initial_states.get(slot_id)
            init_state = init[0] if init else SlotState.EMPTY
            init_mismatch = init[1] if init else False
            timeline.append((start_time, init_state, init_mismatch))

            for ev in events:
                timeline.append((ev.recorded_at, ev.new_state, ev.is_mismatched))

            # Process intervals
            for i in range(len(timeline)):
                interval_start = timeline[i][0]
                interval_end = timeline[i + 1][0] if i + 1 < len(timeline) else end_time
                state = timeline[i][1]
                is_mismatched = timeline[i][2]

                if interval_start >= interval_end:
                    continue

                is_occupied = state in (SlotState.VEHICLE, SlotState.OBSTRUCTED)
                if not is_occupied:
                    continue

                # Split interval into hour-of-day buckets
                self._accumulate_hourly(
                    zone_hourly[zone_id], interval_start, interval_end, is_mismatched
                )

        # --- Aggregate into response ---
        zones_result = []
        all_occupancy_by_hour = {h: {"vehicle_min": 0.0, "total_possible": 0.0} for h in range(24)}

        for zone_id, meta in zone_meta.items():
            total_slots = meta["total_slots"]
            hourly_data = zone_hourly[zone_id]
            possible_per_hour = total_slots * num_days * 60  # minutes

            hourly_breakdown = []
            for h in range(24):
                veh_min = hourly_data[h]["vehicle_min"]
                mis_min = hourly_data[h]["mismatch_min"]
                occ_pct = round(min(veh_min / possible_per_hour * 100, 100), 1) if possible_per_hour > 0 else 0
                mis_pct = round(mis_min / veh_min * 100, 1) if veh_min > 0 else 0
                occupied_slots = round(veh_min / (num_days * 60)) if num_days > 0 else 0

                hourly_breakdown.append({
                    "hour": h,
                    "occupancy_pct": occ_pct,
                    "occupied_slots": min(occupied_slots, total_slots),
                    "total_slots": total_slots,
                    "mismatch_pct": mis_pct,
                })

                all_occupancy_by_hour[h]["vehicle_min"] += veh_min
                all_occupancy_by_hour[h]["total_possible"] += possible_per_hour

            # Find peak periods
            peak_periods = self._find_peak_periods(hourly_breakdown, threshold)

            # Compute zone averages
            total_veh = sum(hourly_data[h]["vehicle_min"] for h in range(24))
            total_mis = sum(hourly_data[h]["mismatch_min"] for h in range(24))
            total_possible = possible_per_hour * 24
            avg_occ = round(min(total_veh / total_possible * 100, 100), 1) if total_possible > 0 else 0
            avg_mis = round(total_mis / total_veh * 100, 1) if total_veh > 0 else 0

            # Generate insight
            insight = self._generate_insight(
                meta["zone_name"], meta["location_name"], meta["floor_label"],
                slot_type, peak_periods, avg_occ, avg_mis,
            )

            zones_result.append({
                "zone_id": str(zone_id),
                "zone_name": meta["zone_name"],
                "floor_label": meta["floor_label"],
                "location_name": meta["location_name"],
                "area_name": meta["area_name"],
                "total_slots": total_slots,
                "slots_by_type": meta["slots_by_type"],
                "avg_occupancy_pct": avg_occ,
                "avg_mismatch_pct": avg_mis,
                "hourly_breakdown": hourly_breakdown,
                "peak_periods": peak_periods,
                "insight": insight,
            })

        # Sort by avg occupancy desc
        zones_result.sort(key=lambda z: z["avg_occupancy_pct"], reverse=True)

        # Global stats
        global_peak_hour = None
        max_global_occ = 0
        total_global_veh = 0
        total_global_possible = 0
        total_global_mis = 0

        for h in range(24):
            veh = all_occupancy_by_hour[h]["vehicle_min"]
            poss = all_occupancy_by_hour[h]["total_possible"]
            total_global_veh += veh
            total_global_possible += poss
            if poss > 0:
                occ = veh / poss
                if occ > max_global_occ:
                    max_global_occ = occ
                    global_peak_hour = h

        # Sum mismatch across all zones
        for zone_id in zone_hourly:
            for h in range(24):
                total_global_mis += zone_hourly[zone_id][h]["mismatch_min"]

        global_avg_occ = round(min(total_global_veh / total_global_possible * 100, 100), 1) if total_global_possible > 0 else 0
        global_avg_mis = round(total_global_mis / total_global_veh * 100, 1) if total_global_veh > 0 else 0

        hotspot_zones = [z["zone_name"] for z in zones_result if z["avg_occupancy_pct"] >= threshold]

        return {
            "threshold": threshold,
            "slot_type_filter": slot_type,
            "start_date": start_time.isoformat(),
            "end_date": end_time.isoformat(),
            "zones": zones_result,
            "global_peak_hour": global_peak_hour,
            "global_avg_occupancy_pct": global_avg_occ,
            "global_avg_mismatch_pct": global_avg_mis,
            "hotspot_zones": hotspot_zones,
        }

    @staticmethod
    def _accumulate_hourly(
        hourly: Dict[int, Dict[str, float]],
        start: datetime,
        end: datetime,
        is_mismatched: bool,
    ) -> None:
        """Split a time interval into hour-of-day buckets and accumulate minutes."""
        current = start
        while current < end:
            hour = current.hour
            # End of this hour-slot: next hour boundary or interval end
            next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            bucket_end = min(next_hour, end)
            minutes = (bucket_end - current).total_seconds() / 60

            hourly[hour]["vehicle_min"] += minutes
            if is_mismatched:
                hourly[hour]["mismatch_min"] += minutes

            current = bucket_end

    @staticmethod
    def _find_peak_periods(
        hourly_breakdown: List[Dict[str, Any]], threshold: int
    ) -> List[Dict[str, Any]]:
        """Find contiguous hour runs where occupancy > threshold."""
        peaks = []
        i = 0
        while i < 24:
            if hourly_breakdown[i]["occupancy_pct"] >= threshold:
                start_h = i
                occ_sum = 0
                mis_sum = 0
                count = 0
                while i < 24 and hourly_breakdown[i]["occupancy_pct"] >= threshold:
                    occ_sum += hourly_breakdown[i]["occupancy_pct"]
                    mis_sum += hourly_breakdown[i]["mismatch_pct"]
                    count += 1
                    i += 1
                end_h = i  # exclusive

                def fmt_hour(h: int) -> str:
                    if h == 0 or h == 24:
                        return "12:00 AM"
                    if h == 12:
                        return "12:00 PM"
                    if h < 12:
                        return f"{h}:00 AM"
                    return f"{h - 12}:00 PM"

                peaks.append({
                    "start_hour": start_h,
                    "end_hour": end_h,
                    "avg_occupancy_pct": round(occ_sum / count, 1),
                    "avg_mismatch_pct": round(mis_sum / count, 1),
                    "label": f"{fmt_hour(start_h)} - {fmt_hour(end_h)}",
                })
            else:
                i += 1
        return peaks

    @staticmethod
    def _generate_insight(
        zone_name: str,
        location_name: str,
        floor_label: str,
        slot_type: Optional[str],
        peak_periods: List[Dict[str, Any]],
        avg_occ: float,
        avg_mis: float,
    ) -> str:
        """Generate a natural language insight string."""
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

    @staticmethod
    def _empty_occupancy_response(
        threshold: int, slot_type: Optional[str],
        start_time: datetime, end_time: datetime,
    ) -> Dict[str, Any]:
        return {
            "threshold": threshold,
            "slot_type_filter": slot_type,
            "start_date": start_time.isoformat(),
            "end_date": end_time.isoformat(),
            "zones": [],
            "global_peak_hour": None,
            "global_avg_occupancy_pct": 0,
            "global_avg_mismatch_pct": 0,
            "hotspot_zones": [],
        }
