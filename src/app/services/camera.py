import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.camera import CameraRepository


class CameraService:
    def __init__(self, camera_repo: CameraRepository):
        self.camera_repo = camera_repo

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

    async def get_by_device_id(self, device_id: uuid.UUID) -> List[Any]:
        return await self.camera_repo.get_by_device_id(device_id)

    async def update(self, camera_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        camera = await self.camera_repo.get_by_id(camera_id)
        if not camera:
            raise NotFoundException(detail="Camera not found")
        return await self.camera_repo.update(camera_id, data)

    async def delete(self, camera_id: uuid.UUID) -> bool:
        camera = await self.camera_repo.get_by_id(camera_id)
        if not camera:
            raise NotFoundException(detail="Camera not found")
        return await self.camera_repo.delete(camera_id)
