import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.models.anpr_camera_config import AnprCameraConfig
from src.app.repositories.anpr_camera_config import AnprCameraConfigRepository


class AnprCameraConfigService:
    def __init__(self, repo: AnprCameraConfigRepository):
        self.repo = repo

    async def get_all(self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None) -> List[AnprCameraConfig]:
        return await self.repo.get_all(skip, limit, filters)

    async def get_by_id(self, config_id: uuid.UUID) -> AnprCameraConfig:
        config = await self.repo.get_by_id(config_id)
        if not config:
            raise NotFoundException(detail="ANPR camera config not found")
        return config

    async def get_by_camera_id(self, camera_id: uuid.UUID) -> Optional[AnprCameraConfig]:
        return await self.repo.get_by_camera_id(camera_id)

    async def create(self, data: Dict[str, Any]) -> AnprCameraConfig:
        return await self.repo.create(data)

    async def update(self, config_id: uuid.UUID, data: Dict[str, Any]) -> AnprCameraConfig:
        config = await self.repo.update(config_id, data)
        if not config:
            raise NotFoundException(detail="ANPR camera config not found")
        return config

    async def delete(self, config_id: uuid.UUID) -> bool:
        return await self.repo.delete(config_id)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.repo.count(filters)
