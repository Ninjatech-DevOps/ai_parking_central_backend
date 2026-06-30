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
    ) -> List[ParkingScan]:
        if interval_minutes and interval_minutes > 0:
            return await self._get_sampled(
                skip, limit, location_id, location_ids, start_date, end_date, interval_minutes
            )
        query = select(ParkingScan)
        query = self._apply_filters(query, location_id, location_ids, start_date, end_date)
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
    ) -> List[ParkingScan]:
        """Return one row per (camera, time-bucket) using DISTINCT ON.

        PostgreSQL's DISTINCT ON picks the first row per group when ordered,
        so we order by recorded_at DESC within each bucket to get the latest
        scan in each interval window.
        """
        bucket = func.date_trunc(
            "hour", ParkingScan.recorded_at
        ) + text(f"(floor(extract(minute from recorded_at) / {interval_minutes}) * {interval_minutes}) * interval '1 minute'")

        query = (
            select(ParkingScan)
            .distinct(ParkingScan.camera_id, bucket)
            .order_by(ParkingScan.camera_id, bucket.desc(), ParkingScan.recorded_at.desc())
        )
        query = self._apply_filters(query, location_id, location_ids, start_date, end_date)

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
    ) -> List[ParkingScan]:
        """Return the most recent scan for each location in scope.

        Uses Postgres DISTINCT ON (location_id) ordered by recorded_at DESC, so
        each location contributes exactly its latest reading. For a single
        location this is just its last entry; with no location filter it returns
        one latest row per location across the scope (to be summed by the caller).

        `since`: only consider scans at/after this time (e.g. start-of-today), so
        locations with no recent reading are excluded — "today's live occupancy".
        """
        query = (
            select(ParkingScan)
            .distinct(ParkingScan.location_id)
            .order_by(ParkingScan.location_id, ParkingScan.recorded_at.desc(), ParkingScan.id.desc())
        )
        query = self._apply_filters(query, location_id, location_ids, since, None)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval_minutes: Optional[int] = None,
    ) -> int:
        if interval_minutes and interval_minutes > 0:
            return await self._count_sampled(
                location_id, location_ids, start_date, end_date, interval_minutes
            )
        query = select(func.count()).select_from(ParkingScan)
        query = self._apply_filters(query, location_id, location_ids, start_date, end_date)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def _count_sampled(self, location_id, location_ids, start_date, end_date, interval_minutes: int) -> int:
        bucket = func.date_trunc(
            "hour", ParkingScan.recorded_at
        ) + text(f"(floor(extract(minute from recorded_at) / {interval_minutes}) * {interval_minutes}) * interval '1 minute'")

        query = (
            select(ParkingScan.id)
            .distinct(ParkingScan.camera_id, bucket)
            .order_by(ParkingScan.camera_id, bucket.desc(), ParkingScan.recorded_at.desc())
        )
        query = self._apply_filters(query, location_id, location_ids, start_date, end_date)
        count_q = select(func.count()).select_from(query.subquery())
        result = await self.db.execute(count_q)
        return result.scalar_one()

    def _apply_filters(self, query, location_id, location_ids, start_date, end_date):
        if location_id:
            query = query.where(ParkingScan.location_id == location_id)
        elif location_ids is not None:
            query = query.where(ParkingScan.location_id.in_(location_ids))
        if start_date:
            query = query.where(ParkingScan.recorded_at >= start_date)
        if end_date:
            query = query.where(ParkingScan.recorded_at <= end_date)
        return query
