import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.device_telemetry import DeviceTelemetry
from src.app.repositories.base import BaseRepository


class DeviceTelemetryRepository(BaseRepository[DeviceTelemetry]):
    def __init__(self, db: AsyncSession):
        super().__init__(DeviceTelemetry, db)

    async def get_latest_by_device(self, device_id: uuid.UUID) -> Optional[DeviceTelemetry]:
        result = await self.db.execute(
            select(DeviceTelemetry)
            .where(DeviceTelemetry.device_id == device_id)
            .order_by(DeviceTelemetry.recorded_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_by_device_id(
        self,
        device_id: uuid.UUID,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[DeviceTelemetry]:
        query = (
            select(DeviceTelemetry)
            .where(DeviceTelemetry.device_id == device_id)
            .order_by(DeviceTelemetry.recorded_at.desc())
            .limit(limit)
        )
        if start_time:
            query = query.where(DeviceTelemetry.recorded_at >= start_time)
        if end_time:
            query = query.where(DeviceTelemetry.recorded_at <= end_time)
        result = await self.db.execute(query)
        return list(result.scalars().all())
