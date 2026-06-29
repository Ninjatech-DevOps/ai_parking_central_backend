import uuid
from typing import Any, Dict, List, Optional

from src.app.core.constants import DeviceStatus
from src.app.exceptions.base import ConflictException, NotFoundException
from src.app.repositories.device import DeviceRepository
from src.app.repositories.location import LocationRepository


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

        # Clear all FK references via raw SQL, then delete device
        from sqlalchemy import text
        db = self.device_repo.db
        did = str(device.id)

        await db.execute(text("DELETE FROM notification_logs WHERE alert_event_id IN (SELECT id FROM alert_events WHERE device_id = :did)"), {"did": did})
        await db.execute(text("DELETE FROM alert_events WHERE device_id = :did"), {"did": did})
        await db.execute(text("DELETE FROM anpr_sessions WHERE entry_record_id IN (SELECT id FROM anpr_records WHERE device_id = :did)"), {"did": did})
        await db.execute(text("DELETE FROM anpr_records WHERE device_id = :did"), {"did": did})
        await db.execute(text("DELETE FROM anpr_camera_configs WHERE camera_id IN (SELECT id FROM cameras WHERE device_id = :did)"), {"did": did})
        await db.execute(text("DELETE FROM parking_scans WHERE device_id = :did"), {"did": did})
        await db.execute(text("DELETE FROM slot_events WHERE device_id = :did"), {"did": did})
        await db.execute(text("DELETE FROM device_telemetry WHERE device_id = :did"), {"did": did})
        await db.execute(text("DELETE FROM device_commands WHERE device_id = :did"), {"did": did})
        await db.execute(text("UPDATE parking_slots SET camera_id = NULL WHERE camera_id IN (SELECT id FROM cameras WHERE device_id = :did)"), {"did": did})
        await db.execute(text("DELETE FROM cameras WHERE device_id = :did"), {"did": did})
        await db.flush()

        return await self.device_repo.delete(id)
