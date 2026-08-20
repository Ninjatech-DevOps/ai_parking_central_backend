import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.parking_scan import ParkingScan
from src.app.repositories.base import BaseRepository


class ParkingScanRepository(BaseRepository[ParkingScan]):
    def __init__(self, db: AsyncSession):
        super().__init__(ParkingScan, db)

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
    ) -> List[ParkingScan]:
        if interval_minutes and interval_minutes > 0:
            return await self._get_sampled(
                skip, limit, location_id, location_ids, start_date, end_date,
                interval_minutes, camera_id=camera_id,
            )
        query = select(ParkingScan)
        query = self._apply_filters(
            query, location_id, location_ids, start_date, end_date, camera_id=camera_id
        )
        # id desc as a deterministic tiebreak so rows that share recorded_at
        # (e.g. demo data) order consistently — and the summary's "latest per
        # location" pick matches the first row shown here.
        query = query.order_by(ParkingScan.recorded_at.desc(), ParkingScan.id.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _get_sampled(
        self,
        skip: int,
        limit: int,
        location_id,
        location_ids,
        start_date,
        end_date,
        interval_minutes: int,
        camera_id: Optional[uuid.UUID] = None,
    ) -> List[ParkingScan]:
        """Return one row per (camera, time-bucket) using DISTINCT ON.

        PostgreSQL's DISTINCT ON picks the first row per group when ordered,
        so we order by recorded_at DESC within each bucket to get the latest
        scan in each interval window.

        A camera_id predicate simply narrows the rows before grouping; the
        DISTINCT ON key stays valid and degenerates to one row per bucket.
        """
        # Clamp defensively: this value is interpolated into raw SQL below, and
        # 0 would divide by zero. Callers bound it too, but not every caller can
        # be trusted to (see public_view's unbounded query param).
        iv = max(1, min(60, int(interval_minutes)))
        bucket = func.date_trunc(
            "hour", ParkingScan.recorded_at
        ) + text(f"(floor(extract(minute from recorded_at) / {iv}) * {iv}) * interval '1 minute'")

        query = (
            select(ParkingScan)
            .distinct(ParkingScan.camera_id, bucket)
            .order_by(ParkingScan.camera_id, bucket.desc(), ParkingScan.recorded_at.desc())
        )
        query = self._apply_filters(
            query, location_id, location_ids, start_date, end_date, camera_id=camera_id
        )

        # Wrap in subquery to apply skip/limit on the sampled result
        subq = query.subquery()
        final = (
            select(ParkingScan)
            .join(subq, ParkingScan.id == subq.c.id)
            .order_by(ParkingScan.recorded_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(final)
        return list(result.scalars().all())

    async def latest_per_location(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        camera_id: Optional[uuid.UUID] = None,
    ) -> List[ParkingScan]:
        """Return the most recent scan for each CAMERA in scope.

        (Method name is legacy — this is latest-per-CAMERA, not per-location.)

        Scans are written per-camera, so a location with multiple cameras has one
        latest row per camera. We DISTINCT ON (camera_id) — not location_id — so
        every camera contributes its latest reading and the caller sums across all
        cameras of a location. This matches the dashboard canvas (which sums all
        slots across all cameras); DISTINCT ON (location_id) kept only ONE camera
        per location and undercounted multi-camera locations.

        Cameras cover disjoint slot sets (each camera's car_total equals its own
        slots' capacity), so summing across cameras does NOT double-count.

        `since`/`until`: only consider scans within this time window.
        """
        query = (
            select(ParkingScan)
            .distinct(ParkingScan.camera_id)
            .order_by(ParkingScan.camera_id, ParkingScan.recorded_at.desc(), ParkingScan.id.desc())
        )
        query = self._apply_filters(
            query, location_id, location_ids, since, until, camera_id=camera_id
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval_minutes: Optional[int] = None,
        camera_id: Optional[uuid.UUID] = None,
    ) -> int:
        if interval_minutes and interval_minutes > 0:
            return await self._count_sampled(
                location_id, location_ids, start_date, end_date,
                interval_minutes, camera_id=camera_id,
            )
        query = select(func.count()).select_from(ParkingScan)
        query = self._apply_filters(
            query, location_id, location_ids, start_date, end_date, camera_id=camera_id
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def _count_sampled(
        self,
        location_id,
        location_ids,
        start_date,
        end_date,
        interval_minutes: int,
        camera_id: Optional[uuid.UUID] = None,
    ) -> int:
        # Same defensive clamp as _get_sampled — interpolated into raw SQL.
        iv = max(1, min(60, int(interval_minutes)))
        bucket = func.date_trunc(
            "hour", ParkingScan.recorded_at
        ) + text(f"(floor(extract(minute from recorded_at) / {iv}) * {iv}) * interval '1 minute'")

        query = (
            select(ParkingScan.id)
            .distinct(ParkingScan.camera_id, bucket)
            .order_by(ParkingScan.camera_id, bucket.desc(), ParkingScan.recorded_at.desc())
        )
        query = self._apply_filters(
            query, location_id, location_ids, start_date, end_date, camera_id=camera_id
        )
        count_q = select(func.count()).select_from(query.subquery())
        result = await self.db.execute(count_q)
        return result.scalar_one()

    def _apply_filters(
        self, query, location_id, location_ids, start_date, end_date, camera_id=None
    ):
        # NOTE: this elif is load-bearing — when location_id is given, the
        # caller's location_ids scope set is intentionally ignored. Callers
        # MUST therefore pre-verify location_id against the user's scope
        # (see verify_location_in_scope) before reaching this method.
        if location_id:
            query = query.where(ParkingScan.location_id == location_id)
        elif location_ids is not None:
            query = query.where(ParkingScan.location_id.in_(location_ids))
        # camera_id is an independent AND — never part of the elif chain above —
        # so a camera filter can never widen the caller's location scope.
        if camera_id:
            query = query.where(ParkingScan.camera_id == camera_id)
        if start_date:
            query = query.where(ParkingScan.recorded_at >= start_date)
        if end_date:
            query = query.where(ParkingScan.recorded_at <= end_date)
        return query
