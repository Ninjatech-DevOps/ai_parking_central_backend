import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.app.models.anpr_session import AnprSession
from src.app.repositories.anpr_session import AnprSessionRepository


class AnprSessionService:
    def __init__(self, repo: AnprSessionRepository):
        self.repo = repo

    async def update(self, id: uuid.UUID, data: Dict[str, Any]):
        return await self.repo.update(id, data)

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 20,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_by: str = "out_time",
        sort_order: str = "desc",
    ) -> List[AnprSession]:
        return await self.repo.get_filtered(
            skip, limit, location_id, location_ids, number_plate, vehicle_type, is_active,
            start_date, end_date, sort_by, sort_order,
        )

    async def count_filtered(
        self,
        location_id: Optional[uuid.UUID] = None,
        location_ids: Optional[Set[uuid.UUID]] = None,
        number_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        return await self.repo.count_filtered(
            location_id, location_ids, number_plate, vehicle_type, is_active, start_date, end_date
        )

    async def count_active_by_location(
        self,
        location_ids: Optional[Set[uuid.UUID]] = None,
        location_id: Optional[uuid.UUID] = None,
    ) -> List[dict]:
        return await self.repo.count_active_by_location(location_ids, location_id)

    @staticmethod
    def format_duration(entry_time: datetime, exit_time: Optional[datetime]) -> Optional[str]:
        if not exit_time:
            return None
        delta = exit_time - entry_time
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "0 min"

        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days > 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hr")
        if minutes > 0 or not parts:
            parts.append(f"{minutes} min")
        return " ".join(parts)
