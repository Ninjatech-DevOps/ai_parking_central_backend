import uuid
from typing import Any, Dict, List, Optional, Tuple

from src.app.core.constants import MovementDirection
from src.app.exceptions.base import NotFoundException
from src.app.models.vehicle_movement import VehicleMovement
from src.app.repositories.vehicle_movement import VehicleMovementRepository
from src.app.schemas.vehicle_movement import VehicleMovementSummary


class VehicleMovementService:
    def __init__(self, repo: VehicleMovementRepository):
        self.repo = repo

    async def create(self, data: Dict[str, Any]) -> VehicleMovement:
        # recorded_at is optional on the way in; dropping the key lets the
        # column's server_default stamp "now" rather than writing an explicit
        # NULL into a NOT NULL column.
        if data.get("recorded_at") is None:
            data.pop("recorded_at", None)
        return await self.repo.create(data)

    async def get(self, movement_id: uuid.UUID) -> VehicleMovement:
        movement = await self.repo.get_by_id(movement_id)
        if not movement:
            raise NotFoundException(detail="Vehicle movement not found")
        return movement

    async def get_with_labels(
        self, movement_id: uuid.UUID
    ) -> Tuple[VehicleMovement, Optional[str], Optional[str]]:
        """Same row as get(), plus the location name and camera label.

        Used wherever a single movement is returned to a client, so one row
        never comes back with fewer fields filled in than the same row inside
        a list page.
        """
        row = await self.repo.get_with_labels(movement_id)
        if not row:
            raise NotFoundException(detail="Vehicle movement not found")
        return row

    async def get_filtered(
        self, skip: int, limit: int, **filters: Any
    ) -> List[Tuple[VehicleMovement, Optional[str], Optional[str]]]:
        return await self.repo.get_filtered(skip=skip, limit=limit, **filters)

    async def count_filtered(self, **filters: Any) -> int:
        return await self.repo.count_filtered(**filters)

    async def summary(self, **filters: Any) -> VehicleMovementSummary:
        totals = await self.repo.direction_totals(**filters)
        total_in = totals.get(MovementDirection.IN.value, 0)
        total_out = totals.get(MovementDirection.OUT.value, 0)
        return VehicleMovementSummary(
            total_in=total_in,
            total_out=total_out,
            net=total_in - total_out,
        )

    async def update(self, movement_id: uuid.UUID, data: Dict[str, Any]) -> VehicleMovement:
        await self.get(movement_id)
        return await self.repo.update(movement_id, data)

    async def delete(self, movement_id: uuid.UUID) -> bool:
        await self.get(movement_id)
        return await self.repo.delete(movement_id)
