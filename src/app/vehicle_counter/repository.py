"""Data access for vehicle events.

Standalone rather than extending ``src.app.repositories.base.BaseRepository``:
that class is typed against the Postgres ``Base``, and its ``update()`` strips
``None`` values -- which would silently turn "clear the number plate" into a
no-op.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.vehicle_counter.models import VehicleEvent


class VehicleEventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> VehicleEvent:
        obj = VehicleEvent(**data)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def get_by_id(
        self, event_id: int, include_deleted: bool = False
    ) -> Optional[VehicleEvent]:
        query = select(VehicleEvent).where(VehicleEvent.id == event_id)
        if not include_deleted:
            query = query.where(VehicleEvent.deleted_at.is_(None))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_paginated(self, skip: int, limit: int) -> List[VehicleEvent]:
        # id is the tiebreaker because timestamps are editable and can collide
        # or fall out of insertion order after an edit.
        query = (
            select(VehicleEvent)
            .where(VehicleEvent.deleted_at.is_(None))
            .order_by(VehicleEvent.timestamp.desc(), VehicleEvent.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def recent(self, limit: int = 10) -> List[VehicleEvent]:
        return await self.list_paginated(0, limit)

    async def count(self) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(VehicleEvent)
            .where(VehicleEvent.deleted_at.is_(None))
        )
        return int(result.scalar_one())

    async def totals(self) -> Tuple[int, int]:
        """Return ``(total_in, total_out)`` in one query."""
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(VehicleEvent.in_count), 0),
                func.coalesce(func.sum(VehicleEvent.out_count), 0),
            ).where(VehicleEvent.deleted_at.is_(None))
        )
        row = result.one()
        return int(row[0]), int(row[1])

    async def list_for_export(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[VehicleEvent]:
        """All non-deleted events in a date range, OLDEST first.

        Ascending on purpose: an export is read top-to-bottom as a timeline,
        so the newest entry belongs at the bottom -- the opposite of the
        on-screen listing.
        """
        query = select(VehicleEvent).where(VehicleEvent.deleted_at.is_(None))
        if start is not None:
            query = query.where(VehicleEvent.timestamp >= start)
        if end is not None:
            query = query.where(VehicleEvent.timestamp <= end)
        query = query.order_by(VehicleEvent.timestamp.asc(), VehicleEvent.id.asc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(self, event_id: int, data: dict) -> Optional[VehicleEvent]:
        """Apply ``data`` to one row.

        Unlike ``BaseRepository.update``, an explicit ``None`` IS written --
        that is how a number plate gets cleared.
        """
        obj = await self.get_by_id(event_id)
        if obj is None:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def soft_delete(self, event_id: int) -> bool:
        """Hide the row without removing it.

        The record stays in the database for audit; clearing ``deleted_at``
        restores it.
        """
        obj = await self.get_by_id(event_id)
        if obj is None:
            return False
        obj.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True
