import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import NotFoundException
from src.app.repositories.alert_event import AlertEventRepository


class AlertEventService:
    def __init__(self, alert_event_repo: AlertEventRepository):
        self.alert_event_repo = alert_event_repo

    async def get(self, alert_event_id: uuid.UUID) -> Any:
        event = await self.alert_event_repo.get_by_id(alert_event_id)
        if not event:
            raise NotFoundException(detail="Alert not found")
        return event

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.alert_event_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.alert_event_repo.count(filters=filters)
