import uuid
from datetime import datetime
from typing import List, Optional, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import VehicleType
from src.app.models.anpr_session import AnprSession
from src.app.repositories.base import BaseRepository


class AnprSessionRepository(BaseRepository[AnprSession]):
    def __init__(self, db: AsyncSession):
        super().__init__(AnprSession, db)

    async def find_active_session(
        self, location_id: uuid.UUID, number_plate: str
    ) -> Optional[AnprSession]:
        result = await self.db.execute(
            select(AnprSession).where(
                AnprSession.location_id == location_id,
                AnprSession.number_plate == number_plate,
                AnprSession.is_active == True,
            )
        )
        return result.scalars().first()

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 20,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_by: str = "out_time",
        sort_order: str = "desc",
    ) -> List[AnprSession]:
        query = select(AnprSession)
        query = self._apply_filters(query, location_id, location_ids, number_plate, vehicle_type, is_active, start_date, end_date)
        col, direction = self._resolve_sort(sort_by, sort_order)
        # exit_time is nullable (still-parked sessions) -> keep those rows last
        # via NULLS LAST; id is a deterministic tiebreak.
        query = (
            query.order_by(direction.nullslast(), AnprSession.id.desc())
            .offset(skip).limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def _resolve_sort(sort_by: str, sort_order: str):
        """Tolerantly map the frontend's sort filter onto an order column +
        direction. Accepts field aliases (out_time/exit_time/out,
        in_time/entry_time/in) and a direction encoded in sort_by itself
        (e.g. 'exit_time_desc', '-exit_time'). Defaults to out-time, desc."""
        sb = (sort_by or "").strip().lower()
        so = (sort_order or "").strip().lower()
        # Direction encoded inside sort_by (single-param frontends).
        if sb.startswith("-"):
            so, sb = "desc", sb[1:]
        elif sb.startswith("+"):
            so, sb = "asc", sb[1:]
        for suffix, d in (("_desc", "desc"), ("_asc", "asc"), (" desc", "desc"), (" asc", "asc")):
            if sb.endswith(suffix):
                so, sb = d, sb[: -len(suffix)]
                break
        in_aliases = {"in_time", "entry_time", "in", "entry", "intime", "entrytime"}
        col = AnprSession.entry_time if sb in in_aliases else AnprSession.exit_time
        direction = col.asc() if so == "asc" else col.desc()
        return col, direction

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        query = select(func.count()).select_from(AnprSession)
        query = self._apply_filters(query, location_id, location_ids, number_plate, vehicle_type, is_active, start_date, end_date)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def count_active_by_location(
        self,
        location_ids: Optional[Set[uuid.UUID]] = None,
        location_id: Optional[uuid.UUID] = None,
    ) -> List[dict]:
        """Count active sessions grouped by location_id and vehicle_type."""
        query = (
            select(
                AnprSession.location_id,
                AnprSession.vehicle_type,
                func.count().label("count"),
            )
            .where(AnprSession.is_active == True)
            .group_by(AnprSession.location_id, AnprSession.vehicle_type)
        )
        if location_id:
            query = query.where(AnprSession.location_id == location_id)
        elif location_ids is not None:
            query = query.where(AnprSession.location_id.in_(location_ids))
        result = await self.db.execute(query)
        return [{"location_id": r[0], "vehicle_type": r[1], "count": r[2]} for r in result.all()]

    def _apply_filters(self, query, location_id, location_ids, number_plate, vehicle_type, is_active, start_date, end_date):
        if location_id:
            query = query.where(AnprSession.location_id == location_id)
        elif location_ids is not None:
            query = query.where(AnprSession.location_id.in_(location_ids))
        if number_plate:
            query = query.where(AnprSession.number_plate.ilike(f"%{number_plate}%"))
        if vehicle_type:
            query = query.where(AnprSession.vehicle_type == vehicle_type)
        if is_active is not None:
            query = query.where(AnprSession.is_active == is_active)
        if start_date:
            query = query.where(AnprSession.entry_time >= start_date)
        if end_date:
            query = query.where(AnprSession.entry_time <= end_date)
        return query
