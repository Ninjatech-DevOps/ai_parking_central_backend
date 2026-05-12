import uuid
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids
from src.app.core.constants import DeviceStatus, Permission
from src.app.db.session import get_db
from src.app.repositories.device import DeviceRepository
from src.app.repositories.location import LocationRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.device import DeviceCreate, DeviceResponse, DeviceUpdate
from src.app.services.device import DeviceService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/devices", tags=["Devices"])


def get_device_service(db: AsyncSession = Depends(get_db)) -> DeviceService:
    return DeviceService(
        device_repo=DeviceRepository(db),
        location_repo=LocationRepository(db),
    )


@router.post("", response_model=DeviceResponse, status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.DEVICES_VIEW))])
async def create_device(
    body: DeviceCreate, service: DeviceService = Depends(get_device_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[DeviceResponse])
async def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    location_id: uuid.UUID = Query(None),
    city_id: uuid.UUID = Query(None),
    status: DeviceStatus = Query(None),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
    db: AsyncSession = Depends(get_db),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if location_id: filters["location_id"] = location_id
    if city_id: filters["city_id"] = city_id
    if status: filters["status"] = status
    repo = DeviceRepository(db)
    items = await repo.get_scoped(user_location_ids, skip=skip, limit=limit, filters=filters or None)
    total = await repo.count_scoped(user_location_ids, filters=filters or None)
    return build_paginated_response(items, total, page, limit)


@router.get("/{device_uuid}", response_model=DeviceResponse)
async def get_device(
    device_uuid: uuid.UUID,
    service: DeviceService = Depends(get_device_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
):
    return await service.get(device_uuid)


@router.patch("/{device_uuid}", response_model=DeviceResponse)
async def update_device(
    device_uuid: uuid.UUID,
    body: DeviceUpdate,
    service: DeviceService = Depends(get_device_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_UPDATE)),
):
    return await service.update(device_uuid, body.model_dump(exclude_unset=True))


@router.delete("/{device_uuid}", response_model=MessageResponse)
async def delete_device(
    device_uuid: uuid.UUID,
    service: DeviceService = Depends(get_device_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_UPDATE)),
):
    await service.delete(device_uuid)
    return MessageResponse(message="Device deleted successfully")
