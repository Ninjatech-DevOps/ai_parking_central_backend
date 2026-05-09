from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.alert_rule import AlertRule
from src.app.repositories.base import BaseRepository


class AlertRuleRepository(BaseRepository[AlertRule]):
    def __init__(self, db: AsyncSession):
        super().__init__(AlertRule, db)

    async def get_active_rules(self) -> List[AlertRule]:
        result = await self.db.execute(
            select(AlertRule).where(AlertRule.is_active == True)
        )
        return list(result.scalars().all())
