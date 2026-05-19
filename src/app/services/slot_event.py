import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, func, text
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
                "entry_time": entry_time.isoformat(),
                "exit_time": exit_time.isoformat() if exit_time else None,
                "duration_minutes": duration_minutes,
                "is_active": exit_time is None,
            })

        return sessions, total
