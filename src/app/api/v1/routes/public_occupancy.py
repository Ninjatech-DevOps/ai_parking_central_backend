from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.session import get_db
from src.app.models.location import Location
from src.app.repositories.parking_scan import ParkingScanRepository
from src.app.services.parking_scan import ParkingScanService

router = APIRouter(prefix="/public", tags=["Public Occupancy"])


@router.get("/occupancy")
async def public_occupancy(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Location).where(Location.is_active == True).order_by(Location.name)
    )
    locations = list(result.scalars().all())

    service = ParkingScanService(ParkingScanRepository(db))
    scans = await service.repo.latest_per_location()

    scan_by_loc: dict = {}
    for s in scans:
        loc_id = str(s.location_id)
        if loc_id not in scan_by_loc:
            scan_by_loc[loc_id] = {
                "car_occupied": 0, "car_available": 0, "car_total": 0,
                "two_wheeler_occupied": 0, "two_wheeler_available": 0, "two_wheeler_total": 0,
            }
        agg = scan_by_loc[loc_id]
        agg["car_occupied"] += s.car_occupied or 0
        agg["car_available"] += s.car_available or 0
        agg["car_total"] += s.car_total or 0
        agg["two_wheeler_occupied"] += s.two_wheeler_occupied or 0
        agg["two_wheeler_available"] += s.two_wheeler_available or 0
        agg["two_wheeler_total"] += s.two_wheeler_total or 0

    items = []
    for loc in locations:
        lid = str(loc.id)
        occ = scan_by_loc.get(lid, {})
        items.append({
            "id": lid,
            "name": loc.name,
            "address": loc.address or "",
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "car_total": occ.get("car_total", loc.total_car_slots),
            "car_occupied": occ.get("car_occupied", 0),
            "car_available": occ.get("car_available", loc.total_car_slots),
            "two_wheeler_total": occ.get("two_wheeler_total", loc.total_two_wheeler_slots),
            "two_wheeler_occupied": occ.get("two_wheeler_occupied", 0),
            "two_wheeler_available": occ.get("two_wheeler_available", loc.total_two_wheeler_slots),
        })

    return {"locations": items}
