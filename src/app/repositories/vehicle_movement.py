import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.camera import Camera
from src.app.models.location import Location
from src.app.models.vehicle_movement import VehicleMovement
from src.app.repositories.base import BaseRepository


class VehicleMovementRepository(BaseRepository[VehicleMovement]):
    def __init__(self, db: AsyncSession):
        super().__init__(VehicleMovement, db)

    def _apply_filters(
        self,
        query,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        camera_id: Optional[uuid.UUID] = None,
        vehicle_type: Optional[str] = None,
        direction: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        number_plate: Optional[str] = None,
    ):
        # A single requested location wins over the caller's scope set, so the
        # caller MUST have already checked it with verify_location_in_scope.
        # Same contract as ParkingScanRepository._apply_filters.
        if location_id:
            query = query.where(VehicleMovement.location_id == location_id)
        elif location_ids is not None:
            # An EMPTY set is a real answer meaning "no locations", and must
            # produce no rows. Callers pass the set through untouched — never
            # `scoped_ids or None`, which would silently drop the filter.
            query = query.where(VehicleMovement.location_id.in_(location_ids))

        # Independent AND: narrowing to a camera can never widen the location
        # scope above it.
        if camera_id:
            query = query.where(VehicleMovement.camera_id == camera_id)
        if vehicle_type:
            query = query.where(VehicleMovement.vehicle_type == vehicle_type)
        if direction:
            query = query.where(VehicleMovement.direction == direction)
        if number_plate:
            query = query.where(VehicleMovement.number_plate.ilike(f"%{number_plate}%"))
        if start_date:
            query = query.where(VehicleMovement.recorded_at >= start_date)
        if end_date:
            query = query.where(VehicleMovement.recorded_at <= end_date)
        return query

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 20,
        **filters: Any,
    ) -> List[Tuple[VehicleMovement, Optional[str], Optional[str]]]:
        """Return (movement, location_name, camera_label) for one page.

        The two labels are selected by outer join rather than through the ORM
        relationships: loading a Camera entity would eager-load every slot it
        owns, which on a 100-row page is thousands of rows nobody asked for.
        """
        query = (
            select(VehicleMovement, Location.name, Camera.position_label)
            .outerjoin(Location, Location.id == VehicleMovement.location_id)
            .outerjoin(Camera, Camera.id == VehicleMovement.camera_id)
        )
        query = self._apply_filters(query, **filters)
        # id as a deterministic tiebreak so rows sharing a timestamp — a device
        # replaying a buffered batch — paginate consistently instead of
        # reshuffling between page 1 and page 2.
        query = (
            query.order_by(VehicleMovement.recorded_at.desc(), VehicleMovement.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def get_with_labels(
        self, movement_id: uuid.UUID
    ) -> Optional[Tuple[VehicleMovement, Optional[str], Optional[str]]]:
        """One movement with its location name and camera label.

        Single-row twin of get_filtered, so a row fetched on its own carries
        the same fields as the same row inside a list page.
        """
        query = (
            select(VehicleMovement, Location.name, Camera.position_label)
            .outerjoin(Location, Location.id == VehicleMovement.location_id)
            .outerjoin(Camera, Camera.id == VehicleMovement.camera_id)
            .where(VehicleMovement.id == movement_id)
        )
        row = (await self.db.execute(query)).first()
        return (row[0], row[1], row[2]) if row else None

    async def count_filtered(self, **filters: Any) -> int:
        query = select(func.count()).select_from(VehicleMovement)
        query = self._apply_filters(query, **filters)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def direction_totals(self, **filters: Any) -> Dict[str, int]:
        """IN and OUT counts for the whole filtered window.

        Grouped in SQL rather than counted in Python so the totals describe
        every matching row, not just the page currently being viewed.
        """
        query = select(VehicleMovement.direction, func.count()).select_from(
            VehicleMovement
        )
        query = self._apply_filters(query, **filters)
        query = query.group_by(VehicleMovement.direction)
        result = await self.db.execute(query)
        # SQLAlchemy hands back MovementDirection members, not plain strings —
        # str() on one gives "MovementDirection.IN", so read .value instead and
        # key the dict on "IN" / "OUT" as callers expect.
        return {
            getattr(direction, "value", direction): count
            for direction, count in result.all()
        }
