import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.app.models.anpr_record import AnprRecord
from src.app.repositories.anpr_record import AnprRecordRepository


class AnprRecordService:
    def __init__(self, repo: AnprRecordRepository):
        self.repo = repo

    async def create(self, data: Dict[str, Any]) -> AnprRecord:
        return await self.repo.create(data)

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 20,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        direction: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AnprRecord]:
        return await self.repo.get_filtered(
            skip, limit, location_id, location_ids, number_plate, vehicle_type, direction, start_date, end_date
        )

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        direction: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        return await self.repo.count_filtered(
            location_id, location_ids, number_plate, vehicle_type, direction, start_date, end_date
        )

    async def update(self, id: uuid.UUID, data: Dict[str, Any]):
        return await self.repo.update(id, data)

    async def search_plates(
        self,
        query_str: str,
        location_ids: Optional[Set[uuid.UUID]] = None,
        limit: int = 10,
    ) -> List[str]:
        return await self.repo.search_plates(query_str, location_ids, limit)
