import uuid
from typing import Any, Dict, List, Optional

from src.app.core.constants import DeviceStatus
from src.app.exceptions.base import ConflictException, NotFoundException
from src.app.repositories.device import DeviceRepository
from src.app.repositories.location import LocationRepository
from src.app.repositories.base import BaseRepository
from src.app.models.camera import Camera
from src.app.models.parking_slot import ParkingSlot


class DeviceService:
    def __init__(self, device_repo: DeviceRepository, location_repo: LocationRepository):
        self.device_repo = device_repo
        self.location_repo = location_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        existing = await self.device_repo.get_by_device_id(data["device_id"])
        if existing:
            raise ConflictException(detail="Device ID already registered")

        # Auto-populate denormalized city_id from the location
        location = await self.location_repo.get_by_id(data["location_id"])
        if not location:
            raise NotFoundException(detail="Location not found")
        data["city_id"] = location.city_id

        return await self.device_repo.create(data)

    async def get(self, id: uuid.UUID) -> Any:
        device = await self.device_repo.get_by_id(id)
        if not device:
            raise NotFoundException(detail="Device not found")
        return device

    async def get_by_device_id(self, device_id: str) -> Any:
        device = await self.device_repo.get_by_device_id(device_id)
        if not device:
            raise NotFoundException(detail="Device not found")
        return device

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.device_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.device_repo.count(filters=filters)

    async def update(self, id: uuid.UUID, data: Dict[str, Any]) -> Any:
        device = await self.device_repo.get_by_id(id)
        if not device:
            raise NotFoundException(detail="Device not found")

        # If location_id is being changed, re-populate city_id
        if "location_id" in data and data["location_id"]:
            location = await self.location_repo.get_by_id(data["location_id"])
            if location:
                data["city_id"] = location.city_id

        return await self.device_repo.update(id, data)

    async def update_status(self, device_id: str, status: DeviceStatus) -> Any:
        device = await self.device_repo.get_by_device_id(device_id)
        if not device:
            raise NotFoundException(detail="Device not found")
        return await self.device_repo.update(device.id, {"status": status})

    async def delete(self, id: uuid.UUID):
        device = await self.device_repo.get_by_id(id)
        if not device:
            raise NotFoundException(detail="Device not found")

        # Unassign slots from this device's cameras, then delete cameras
        from sqlalchemy import select, update, delete as sa_delete
        db = self.device_repo.db
        for cam in (device.cameras or []):
            await db.execute(update(ParkingSlot).where(ParkingSlot.camera_id == cam.id).values(camera_id=None))
            await db.execute(sa_delete(Camera).where(Camera.id == cam.id))
        await db.flush()

        return await self.device_repo.delete(id)
