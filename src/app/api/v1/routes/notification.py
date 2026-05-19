import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import get_current_user
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.repositories.notification_log import NotificationLogRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.notification_log import InAppNotificationResponse
from src.app.services.notification import NotificationService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def get_notif_service(db: AsyncSession = Depends(get_db)) -> NotificationService:
    return NotificationService(notif_repo=NotificationLogRepository(db))


@router.get("/me", response_model=PaginatedResponse[InAppNotificationResponse])
async def get_my_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    is_read: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notif_service),
):
    """Get current user's in-app notifications."""
    skip, limit = get_pagination_params(page, page_size)
    items = await service.get_user_notifications(
        current_user.id, is_read=is_read, skip=skip, limit=limit
    )
    total = await service.get_total_count(current_user.id, is_read=is_read)
    return build_paginated_response(items, total, page, limit)


@router.get("/me/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notif_service),
):
    """Get count of unread in-app notifications."""
    count = await service.get_unread_count(current_user.id)
    return {"unread_count": count}


@router.patch("/{notification_id}/read", response_model=MessageResponse)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notif_service),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    success = await service.mark_read(notification_id, current_user.id)
    await db.commit()
    if not success:
        return MessageResponse(message="Notification not found", success=False)
    return MessageResponse(message="Marked as read")


@router.patch("/me/read-all", response_model=MessageResponse)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notif_service),
    db: AsyncSession = Depends(get_db),
):
    """Mark all in-app notifications as read."""
    count = await service.mark_all_read(current_user.id)
    await db.commit()
    return MessageResponse(message=f"Marked {count} notification(s) as read")
