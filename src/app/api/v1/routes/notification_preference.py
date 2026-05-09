from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_current_user
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.repositories.notification_preference import NotificationPreferenceRepository
from src.app.schemas.notification_preference import (
    NotificationPreferenceBulkUpdate,
    NotificationPreferenceResponse,
)
from src.app.services.notification_preference import NotificationPreferenceService

router = APIRouter(prefix="/notification-preferences", tags=["Notification Preferences"])


def get_pref_service(db: AsyncSession = Depends(get_db)) -> NotificationPreferenceService:
    return NotificationPreferenceService(
        pref_repo=NotificationPreferenceRepository(db),
    )


@router.get("/me", response_model=List[NotificationPreferenceResponse])
async def get_my_preferences(
    current_user: User = Depends(get_current_user),
    service: NotificationPreferenceService = Depends(get_pref_service),
):
    """Get current user's notification preferences."""
    return await service.get_user_preferences(current_user.id)


@router.put("/me", response_model=List[NotificationPreferenceResponse])
async def update_my_preferences(
    body: NotificationPreferenceBulkUpdate,
    current_user: User = Depends(get_current_user),
    service: NotificationPreferenceService = Depends(get_pref_service),
):
    """Set all notification preferences at once. Replaces existing."""
    return await service.bulk_update(
        current_user.id,
        [p.model_dump() for p in body.preferences],
    )
