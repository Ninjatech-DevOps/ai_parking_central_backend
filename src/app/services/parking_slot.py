import uuid
from typing import Any, Dict, List, Optional

from src.app.core.constants import SlotState
from src.app.exceptions.base import NotFoundException
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.repositories.slot_event import SlotEventRepository


class ParkingSlotService:
    def __init__(
        self,
        slot_repo: ParkingSlotRepository,
        event_repo: SlotEventRepository,
    ):
        self.slot_repo = slot_repo
        self.event_repo = event_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        return await self.slot_repo.create(data)

    async def get(self, slot_id: uuid.UUID) -> Any:
        slot = await self.slot_repo.get_by_id(slot_id)
        if not slot:
            raise NotFoundException(detail="Parking slot not found")
        return slot

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.slot_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.slot_repo.count(filters=filters)

    async def get_by_zone_id(self, zone_id: uuid.UUID) -> List[Any]:
        return await self.slot_repo.get_by_zone_id(zone_id)

    async def update_state(
        self, slot_id: uuid.UUID, new_state: SlotState, device_id: uuid.UUID = None
    ) -> Any:
        slot = await self.slot_repo.get_by_id(slot_id)
        if not slot:
            raise NotFoundException(detail="Parking slot not found")

        previous_state = slot.state

        await self.event_repo.create({
            "parking_slot_id": slot_id,
            "previous_state": previous_state,
            "new_state": new_state,
            "device_id": device_id,
        })

        return await self.slot_repo.update_state(slot_id, new_state)

    async def get_occupancy_stats(self, zone_id: uuid.UUID) -> dict:
        return await self.slot_repo.count_by_state(zone_id)

    async def update(self, slot_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        slot = await self.slot_repo.get_by_id(slot_id)
        if not slot:
            raise NotFoundException(detail="Parking slot not found")
        return await self.slot_repo.update(slot_id, data)

    async def delete(self, slot_id: uuid.UUID) -> bool:
        slot = await self.slot_repo.get_by_id(slot_id)
        if not slot:
            raise NotFoundException(detail="Parking slot not found")
        await self.slot_repo.soft_delete(slot_id)
        return True
