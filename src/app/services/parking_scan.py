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
        camera_id: Optional[uuid.UUID] = None,
        hours_ist: Optional[tuple] = None,
    ) -> List[ParkingScan]:
        return await self.repo.get_filtered(
            skip=skip,
            limit=limit,
            location_id=location_id,
            location_ids=location_ids,
            start_date=start_date,
            end_date=end_date,
            interval_minutes=interval_minutes,
            camera_id=camera_id,
            hours_ist=hours_ist,
        )

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval_minutes: Optional[int] = None,
        camera_id: Optional[uuid.UUID] = None,
        hours_ist: Optional[tuple] = None,
    ) -> int:
        return await self.repo.count_filtered(
            location_id=location_id,
            location_ids=location_ids,
            start_date=start_date,
            end_date=end_date,
            interval_minutes=interval_minutes,
            camera_id=camera_id,
            hours_ist=hours_ist,
        )

    async def current_occupancy_summary(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        camera_id: Optional[uuid.UUID] = None,
        active_cameras_only: bool = False,
        hours_ist: Optional[tuple] = None,
    ) -> Dict[str, Any]:
        """Current occupancy = each camera's latest scan, summed across scope.

        Single location -> sum of ALL that location's cameras, across every
        device. All locations -> sum of every camera's latest entry. Cameras
        cover disjoint slot sets, so summing does not double-count.

        Shared by the AI Parking History summary tiles, the parking PDF summary
        cards, and the public shared-link summary — but no longer identical
        across them: the tiles pass active_cameras_only=True, the others do not,
        so a location with deactivated cameras reports a lower total on the
        tiles than in the PDF or on the public board. That divergence is
        intentional; the public-facing numbers were deliberately left alone.

        `since`/`until`: only consider scans within this time window.
        `camera_id`: narrow to a single camera (tiles then describe that camera).
        `active_cameras_only`: exclude scans from cameras with is_active=False
            (see ParkingScanRepository.latest_per_location for why this matters).
        `hours_ist`: (start_hour, end_hour) confining the "latest" pick to those
            IST hours on every day in range, so the public page reports the last
            reading of the operating day rather than an overnight one.
        """
        scans = await self.repo.latest_per_location(
            location_id=location_id,
            location_ids=location_ids,
            since=since,
            until=until,
            camera_id=camera_id,
            active_cameras_only=active_cameras_only,
            hours_ist=hours_ist,
        )
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
