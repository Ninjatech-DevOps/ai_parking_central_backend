import uuid
from typing import Any, Dict, List, Optional

from src.app.core.constants import DeviceStatus
from src.app.exceptions.base import ConflictException, NotFoundException
from src.app.repositories.device import DeviceRepository


class DeviceService:
    def __init__(self, device_repo: DeviceRepository):
        self.device_repo = device_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        existing = await self.device_repo.get_by_device_id(data["device_id"])
        if existing:
            raise ConflictException(detail="Device ID already registered")
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

    async def get_by_location_ids(self, location_ids: List[uuid.UUID]) -> List[Any]:
        return await self.device_repo.get_by_location_ids(location_ids)

    async def update(self, id: uuid.UUID, data: Dict[str, Any]) -> Any:
        device = await self.device_repo.get_by_id(id)
        if not device:
            raise NotFoundException(detail="Device not found")
        return await self.device_repo.update(id, data)

    async def update_status(self, device_id: str, status: DeviceStatus) -> Any:
        device = await self.device_repo.get_by_device_id(device_id)
        if not device:
            raise NotFoundException(detail="Device not found")
        return await self.device_repo.update(device.id, {"status": status})

    async def delete(self, id: uuid.UUID) -> bool:
        device = await self.device_repo.get_by_id(id)
        if not device:
            raise NotFoundException(detail="Device not found")
        return await self.device_repo.delete(id)
