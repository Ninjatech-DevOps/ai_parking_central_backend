import uuid
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.camera import CameraRepository
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.camera import (
    CameraCreate, CameraResponse, CameraUpdate, SlotConfigRequest,
)
from src.app.services.camera import CameraService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def get_camera_service(db: AsyncSession = Depends(get_db)) -> CameraService:
    return CameraService(
        camera_repo=CameraRepository(db),
        slot_repo=ParkingSlotRepository(db),
    )


@router.post("", response_model=CameraResponse, status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.DEVICES_VIEW))])
async def create_camera(
    body: CameraCreate, service: CameraService = Depends(get_camera_service)
):
    return await service.create(body.model_dump())


@router.get("", response_model=PaginatedResponse[CameraResponse])
async def list_cameras(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    device_id: uuid.UUID = Query(None),
    service: CameraService = Depends(get_camera_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if device_id: filters["device_id"] = device_id
    items = await service.get_all(skip=skip, limit=limit, filters=filters or None)
    total = await service.count(filters=filters or None)
    return build_paginated_response(items, total, page, limit)


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: uuid.UUID,
    service: CameraService = Depends(get_camera_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
):
    return await service.get(camera_id)


@router.patch("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: uuid.UUID,
    body: CameraUpdate,
    service: CameraService = Depends(get_camera_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_UPDATE)),
):
    return await service.update(camera_id, body.model_dump(exclude_unset=True))


@router.delete("/{camera_id}", response_model=MessageResponse)
async def delete_camera(
    camera_id: uuid.UUID,
    service: CameraService = Depends(get_camera_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_UPDATE)),
):
    await service.delete(camera_id)
    return MessageResponse(message="Camera deleted successfully")


@router.post("/{camera_id}/slot-config", response_model=CameraResponse)
async def apply_slot_config(
    camera_id: uuid.UUID,
    body: SlotConfigRequest,
    service: CameraService = Depends(get_camera_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_UPDATE)),
):
    """Client pushes slot position config for a camera."""
    return await service.apply_slot_config(
        camera_id, [s.model_dump() for s in body.slots]
    )
