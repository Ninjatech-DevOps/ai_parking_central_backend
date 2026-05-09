import uuid
from typing import Any, List

from src.app.repositories.notification_preference import NotificationPreferenceRepository


class NotificationPreferenceService:
    def __init__(self, pref_repo: NotificationPreferenceRepository):
        self.pref_repo = pref_repo

    async def get_user_preferences(self, user_id: uuid.UUID) -> List[Any]:
        return await self.pref_repo.get_by_user_id(user_id)

    async def bulk_update(
        self, user_id: uuid.UUID, preferences: list[dict]
    ) -> List[Any]:
        """Replace all preferences for a user."""
        await self.pref_repo.delete_by_user_id(user_id)

        for pref in preferences:
            await self.pref_repo.create({
                "user_id": user_id,
                "alert_severity": pref["alert_severity"],
                "channel": pref["channel"],
                "is_enabled": pref["is_enabled"],
            })

        return await self.pref_repo.get_by_user_id(user_id)
