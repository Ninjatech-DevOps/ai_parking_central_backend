from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import OTAStatus
from src.app.models.ota_deployment import OTADeployment
from src.app.repositories.base import BaseRepository


class OTADeploymentRepository(BaseRepository[OTADeployment]):
    def __init__(self, db: AsyncSession):
        super().__init__(OTADeployment, db)

    async def get_active(self) -> Optional[OTADeployment]:
        result = await self.db.execute(
            select(OTADeployment).where(
                OTADeployment.status == OTAStatus.IN_PROGRESS
            )
        )
        return result.scalars().first()

    async def get_by_status(self, status: OTAStatus) -> List[OTADeployment]:
        result = await self.db.execute(
            select(OTADeployment)
            .where(OTADeployment.status == status)
            .order_by(OTADeployment.created_at.desc())
        )
        return list(result.scalars().all())
