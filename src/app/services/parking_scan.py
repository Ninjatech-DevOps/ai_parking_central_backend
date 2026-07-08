import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.app.models.parking_scan import ParkingScan
from src.app.repositories.parking_scan import ParkingScanRepository


class ParkingScanService:
    def __init__(self, repo: ParkingScanRepository):
        self.repo = repo

    async def create(self, data: Dict[str, Any]) -> ParkingScan:
        return await self.repo.create(data)

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 20,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval_minutes: Optional[int] = None,
    ) -> List[ParkingScan]:
        return await self.repo.get_filtered(
            skip, limit, location_id, location_ids, start_date, end_date, interval_minutes
        )

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval_minutes: Optional[int] = None,
    ) -> int:
        return await self.repo.count_filtered(
            location_id, location_ids, start_date, end_date, interval_minutes
        )

    async def current_occupancy_summary(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Current occupancy = each camera's latest scan, summed across scope.

        Single location -> sum of that location's cameras. All locations -> sum
        of every camera's latest entry. Shared source of truth for the parking
        PDF summary cards and the ANPR PDF occupancy cards.

        `since`/`until`: only consider scans within this time window.
        """
        scans = await self.repo.latest_per_location(location_id, location_ids, since, until)
        car = {"total": 0, "occupied": 0, "available": 0}
        bike = {"total": 0, "occupied": 0, "available": 0}
        latest_recorded_at: Optional[datetime] = None
        for s in scans:
            car["total"] += s.car_total or 0
            car["occupied"] += s.car_occupied or 0
            car["available"] += s.car_available or 0
            bike["total"] += s.two_wheeler_total or 0
            bike["occupied"] += s.two_wheeler_occupied or 0
            bike["available"] += s.two_wheeler_available or 0
            if latest_recorded_at is None or s.recorded_at > latest_recorded_at:
                latest_recorded_at = s.recorded_at
        return {
            "car": car,
            "bike": bike,
            # scans are now per-camera; count distinct locations, not rows.
            "location_count": len({s.location_id for s in scans}),
            "latest_recorded_at": latest_recorded_at,
        }

    async def update_scan(self, scan_id: uuid.UUID, data: Dict[str, Any]) -> ParkingScan:
        return await self.repo.update(scan_id, data)
