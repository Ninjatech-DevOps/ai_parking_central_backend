import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.app.models.parking_scan import ParkingScan
from src.app.repositories.parking_scan import ParkingScanRepository


class ParkingScanService:
    def __init__(self, repo: ParkingScanRepository):
        self.repo = repo

    async def create(self, data: Dict[str, Any]) -> ParkingScan:
        return await self.repo.create(data)

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 20,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[ParkingScan]:
        return await self.repo.get_filtered(
            skip, limit, location_id, location_ids, start_date, end_date
        )

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        return await self.repo.count_filtered(
            location_id, location_ids, start_date, end_date
        )
