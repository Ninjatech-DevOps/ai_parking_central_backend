import uuid
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, verify_location_in_scope
from src.app.core.constants import Permission, SlotState, VehicleType
from src.app.db.session import get_db
from src.app.models.anpr_session import AnprSession
from src.app.models.location import Location
from src.app.models.parking_slot import ParkingSlot
from src.app.models.zone import Zone
from src.app.models.floor import Floor

router = APIRouter(prefix="/anpr-dashboard", tags=["ANPR Dashboard"])


@router.get("/summary")
async def get_dashboard_summary(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.ANPR_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)

    # Resolve scoped location IDs
    scoped_ids = user_location_ids
    if area_id:
        result = await db.execute(select(Location.id).where(Location.area_id == area_id))
        area_loc_ids = {row[0] for row in result.all()}
        scoped_ids = (scoped_ids & area_loc_ids) if scoped_ids is not None else area_loc_ids

    # Get location totals
    loc_q = select(
        func.coalesce(func.sum(Location.total_car_slots), 0).label("car_total"),
        func.coalesce(func.sum(Location.total_two_wheeler_slots), 0).label("tw_total"),
    ).where(Location.is_active == True)
    if location_id:
        loc_q = loc_q.where(Location.id == location_id)
    elif scoped_ids is not None:
        loc_q = loc_q.where(Location.id.in_(scoped_ids))
    loc_row = (await db.execute(loc_q)).one()
    car_total = loc_row.car_total
    tw_total = loc_row.tw_total

    # Count active sessions by vehicle type
    session_q = (
        select(AnprSession.vehicle_type, func.count().label("count"))
        .where(AnprSession.is_active == True)
        .group_by(AnprSession.vehicle_type)
    )
    if location_id:
        session_q = session_q.where(AnprSession.location_id == location_id)
    elif scoped_ids is not None:
        session_q = session_q.where(AnprSession.location_id.in_(scoped_ids))
    session_rows = (await db.execute(session_q)).all()

    car_occupied = 0
    tw_occupied = 0
    for vtype, count in session_rows:
        if vtype == VehicleType.CAR:
            car_occupied = count
        elif vtype == VehicleType.TWO_WHEELER:
            tw_occupied = count

    # Count obstructions from AI Parking slots at same locations
    obs_q = (
        select(func.count())
        .select_from(ParkingSlot)
        .join(Zone, Zone.id == ParkingSlot.zone_id)
        .join(Floor, Floor.id == Zone.floor_id)
        .where(ParkingSlot.is_active == True, ParkingSlot.state == SlotState.OBSTRUCTED)
    )
    if location_id:
        obs_q = obs_q.where(Floor.location_id == location_id)
    elif scoped_ids is not None:
        obs_q = obs_q.where(Floor.location_id.in_(scoped_ids))
    obstructions = (await db.execute(obs_q)).scalar_one()

    return {
        "car_total": car_total,
        "car_occupied": car_occupied,
        "car_available": max(0, car_total - car_occupied),
        "two_wheeler_total": tw_total,
        "two_wheeler_occupied": tw_occupied,
        "two_wheeler_available": max(0, tw_total - tw_occupied),
        "obstructions": obstructions,
    }


@router.get("/locations")
async def get_dashboard_locations(
    area_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.ANPR_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    if location_id:
        verify_location_in_scope(location_id, user_location_ids)

    # Get all locations in scope
    loc_q = select(Location).where(Location.is_active == True)
    if location_id:
        loc_q = loc_q.where(Location.id == location_id)
    elif area_id:
        loc_q = loc_q.where(Location.area_id == area_id)
    if user_location_ids is not None:
        loc_q = loc_q.where(Location.id.in_(user_location_ids))
    locations = (await db.execute(loc_q)).scalars().all()

    # Get active session counts grouped by location + vehicle_type
    session_q = (
        select(
            AnprSession.location_id,
            AnprSession.vehicle_type,
            func.count().label("count"),
        )
        .where(AnprSession.is_active == True)
        .group_by(AnprSession.location_id, AnprSession.vehicle_type)
    )
    if location_id:
        session_q = session_q.where(AnprSession.location_id == location_id)
    elif user_location_ids is not None:
        session_q = session_q.where(AnprSession.location_id.in_(user_location_ids))
    session_rows = (await db.execute(session_q)).all()

    # Build lookup: location_id -> {CAR: count, TWO_WHEELER: count}
    occ_map = {}
    for loc_id, vtype, count in session_rows:
        if loc_id not in occ_map:
            occ_map[loc_id] = {}
        occ_map[loc_id][vtype] = count

    # Count obstructions per location
    obs_q = (
        select(Floor.location_id, func.count().label("count"))
        .select_from(ParkingSlot)
        .join(Zone, Zone.id == ParkingSlot.zone_id)
        .join(Floor, Floor.id == Zone.floor_id)
        .where(ParkingSlot.is_active == True, ParkingSlot.state == SlotState.OBSTRUCTED)
        .group_by(Floor.location_id)
    )
    if user_location_ids is not None:
        obs_q = obs_q.where(Floor.location_id.in_(user_location_ids))
    obs_rows = (await db.execute(obs_q)).all()
    obs_map = {loc_id: count for loc_id, count in obs_rows}

    result = []
    for loc in locations:
        occ = occ_map.get(loc.id, {})
        car_occ = occ.get(VehicleType.CAR, 0)
        tw_occ = occ.get(VehicleType.TWO_WHEELER, 0)
        car_total = loc.total_car_slots
        tw_total = loc.total_two_wheeler_slots
        total = car_total + tw_total
        occupied = car_occ + tw_occ
        obs = obs_map.get(loc.id, 0)

        result.append({
            "location_id": str(loc.id),
            "location_name": loc.name,
            "car_total": car_total,
            "car_occupied": car_occ,
            "car_available": max(0, car_total - car_occ),
            "two_wheeler_total": tw_total,
            "two_wheeler_occupied": tw_occ,
            "two_wheeler_available": max(0, tw_total - tw_occ),
            "obstructions": obs,
            "occupancy_pct": round((occupied / total * 100), 1) if total > 0 else 0,
            "availability_pct": round(((total - occupied) / total * 100), 1) if total > 0 else 100,
        })

    return {"locations": result}
