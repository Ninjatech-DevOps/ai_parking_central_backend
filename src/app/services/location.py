import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.area import AreaRepository
from src.app.repositories.location import LocationRepository


class LocationService:
    def __init__(self, location_repo: LocationRepository, area_repo: AreaRepository):
        self.location_repo = location_repo
        self.area_repo = area_repo

    async def create(self, data: Dict[str, Any]) -> Any:
        # If area_id provided, auto-populate ancestors from it
        if data.get("area_id"):
            area = await self.area_repo.get_by_id(data["area_id"])
            if area:
                data["city_id"] = area.city_id
                data["taluka_id"] = area.taluka_id
                data["village_id"] = area.village_id

        # city_id is required — must come from area or directly
        if not data.get("city_id"):
            raise NotFoundException(detail="city_id is required")

        return await self.location_repo.create(data)

    async def get(self, location_id: uuid.UUID) -> Any:
        location = await self.location_repo.get_by_id(location_id)
        if not location:
            raise NotFoundException(detail="Location not found")
        return location

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.location_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.location_repo.count(filters=filters)

    async def update(self, location_id: uuid.UUID, data: Dict[str, Any]) -> Any:
        location = await self.location_repo.get_by_id(location_id)
        if not location:
            raise NotFoundException(detail="Location not found")

        # If area_id is being changed, re-populate ancestors
        if "area_id" in data and data["area_id"]:
            area = await self.area_repo.get_by_id(data["area_id"])
            if area:
                data["city_id"] = area.city_id
                data["taluka_id"] = area.taluka_id
                data["village_id"] = area.village_id

        return await self.location_repo.update(location_id, data)

    async def delete(self, location_id: uuid.UUID) -> Any:
        location = await self.location_repo.get_by_id(location_id)
        if not location:
            raise NotFoundException(detail="Location not found")
        return await self.location_repo.update(location_id, {"is_active": False})
