import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.camera import CameraRepository
from src.app.repositories.parking_slot import ParkingSlotRepository


class CameraService:
    def __init__(self, camera_repo: CameraRepository, slot_repo: ParkingSlotRepository):
        self.camera_repo = camera_repo
        self.slot_repo = slot_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        return await self.camera_repo.create(data)

    async def get(self, camera_id: uuid.UUID) -> Any:
        camera = await self.camera_repo.get_by_id(camera_id)
        if not camera:
            raise NotFoundException(detail="Camera not found")
        return camera

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.camera_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.camera_repo.count(filters=filters)

    async def update(self, camera_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        camera = await self.camera_repo.get_by_id(camera_id)
        if not camera:
            raise NotFoundException(detail="Camera not found")
        return await self.camera_repo.update(camera_id, data)

    async def delete(self, camera_id: uuid.UUID) -> Any:
        camera = await self.camera_repo.get_by_id(camera_id)
        if not camera:
            raise NotFoundException(detail="Camera not found")
        return await self.camera_repo.update(camera_id, {"is_active": False})

    async def apply_slot_config(self, camera_id: uuid.UUID, slots: List[Dict]) -> Any:
        """Client pushes slot positions for a camera."""
        camera = await self.camera_repo.get_by_id(camera_id)
        if not camera:
            raise NotFoundException(detail="Camera not found")

        for slot_data in slots:
            slot = await self.slot_repo.get_by_id(slot_data["slot_id"])
            if slot:
                update_data = {
                    "camera_id": camera_id,
                    "pos_x1": slot_data["pos_x1"],
                    "pos_y1": slot_data["pos_y1"],
                    "pos_x2": slot_data["pos_x2"],
                    "pos_y2": slot_data["pos_y2"],
                }
                if "polygon_coords" in slot_data and slot_data["polygon_coords"]:
                    update_data["polygon_coords"] = slot_data["polygon_coords"]
                await self.slot_repo.update(slot.id, update_data)

        return camera
