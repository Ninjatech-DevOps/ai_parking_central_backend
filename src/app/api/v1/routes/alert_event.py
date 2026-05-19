import uuid
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, get_current_user
from src.app.core.constants import AlertSeverity, Permission
from src.app.db.session import get_db
from src.app.repositories.alert_event import AlertEventRepository
from src.app.schemas.alert_event import AlertEventResponse
from src.app.schemas.base import PaginatedResponse
from src.app.services.alert_event import AlertEventService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def get_alert_service(db: AsyncSession = Depends(get_db)) -> AlertEventService:
    return AlertEventService(alert_event_repo=AlertEventRepository(db))


@router.get("", response_model=PaginatedResponse[AlertEventResponse])
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    severity: AlertSeverity = Query(None),
    location_id: uuid.UUID = Query(None),
    area_id: uuid.UUID = Query(None),
    city_id: uuid.UUID = Query(None),
    _: bool = Depends(PermissionChecker(Permission.ALERTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if severity:
        filters["severity"] = severity
    if location_id:
        filters["location_id"] = location_id

    # Narrow scope by area or city
    scoped_ids = user_location_ids
    if area_id or city_id:
        from sqlalchemy import select as sa_select
        from src.app.models.location import Location
        q = sa_select(Location.id)
        if area_id:
            q = q.where(Location.area_id == area_id)
        elif city_id:
            q = q.where(Location.city_id == city_id)
        result = await db.execute(q)
        filter_loc_ids = {row[0] for row in result.all()}
        if scoped_ids is not None:
            scoped_ids = scoped_ids & filter_loc_ids
        else:
            scoped_ids = filter_loc_ids

    repo = AlertEventRepository(db)
    items = await repo.get_scoped(scoped_ids, skip=skip, limit=limit, filters=filters or None)
    total = await repo.count_scoped(scoped_ids, filters=filters or None)
    return build_paginated_response(items, total, page, limit)


@router.get("/{alert_id}", response_model=AlertEventResponse)
async def get_alert(
    alert_id: uuid.UUID,
    service: AlertEventService = Depends(get_alert_service),
    _: bool = Depends(PermissionChecker(Permission.ALERTS_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    alert = await service.get(alert_id)
    if alert.location_id:
        from src.app.api.deps import verify_location_in_scope
        verify_location_in_scope(alert.location_id, user_location_ids)
    return alert


@router.patch("/{alert_id}/acknowledge", response_model=AlertEventResponse)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    service: AlertEventService = Depends(get_alert_service),
    _: bool = Depends(PermissionChecker(Permission.ALERTS_ACKNOWLEDGE)),
    current_user=Depends(get_current_user),
):
    return await service.acknowledge(alert_id, current_user.id)


@router.patch("/{alert_id}/resolve", response_model=AlertEventResponse)
async def resolve_alert(
    alert_id: uuid.UUID,
    service: AlertEventService = Depends(get_alert_service),
    _: bool = Depends(PermissionChecker(Permission.ALERTS_ACKNOWLEDGE)),
):
    return await service.resolve(alert_id)
