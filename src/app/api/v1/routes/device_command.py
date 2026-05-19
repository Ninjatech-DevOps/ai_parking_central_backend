import uuid
from typing import List, Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_current_user, get_user_location_ids, verify_location_in_scope
from src.app.core.constants import CommandType, Permission
from src.app.db.session import get_db
from src.app.models.user import User
from src.app.repositories.device import DeviceRepository
from src.app.repositories.device_command import DeviceCommandRepository
from src.app.schemas.base import PaginatedResponse
from src.app.schemas.device_command import (
    DeviceCommandCreate,
    DeviceCommandResponse,
)
from src.app.services.device_command import DeviceCommandService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/device-commands", tags=["Device Commands"])


async def _verify_device_scope(
    device_uuid: uuid.UUID,
    user_location_ids: Optional[Set[uuid.UUID]],
    db: AsyncSession,
) -> None:
    """Resolve device → location_id, then check scope."""
    device = await DeviceRepository(db).get_by_id(device_uuid)
    if device:
        verify_location_in_scope(device.location_id, user_location_ids)


def get_command_service(db: AsyncSession = Depends(get_db)) -> DeviceCommandService:
    return DeviceCommandService(
        command_repo=DeviceCommandRepository(db),
        device_repo=DeviceRepository(db),
    )


@router.post("", response_model=DeviceCommandResponse, status_code=201)
async def send_command(
    body: DeviceCommandCreate,
    current_user: User = Depends(get_current_user),
    service: DeviceCommandService = Depends(get_command_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_RESTART)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_device_scope(body.device_id, user_location_ids, db)
    return await service.send_command(
        device_uuid=body.device_id,
        command_type=body.command_type,
        payload=body.payload,
        sent_by=current_user.id,
    )


@router.post(
    "/{device_uuid}/restart",
    response_model=DeviceCommandResponse,
    status_code=201,
)
async def restart_device(
    device_uuid: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DeviceCommandService = Depends(get_command_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_RESTART)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_device_scope(device_uuid, user_location_ids, db)
    return await service.send_command(
        device_uuid=device_uuid,
        command_type=CommandType.RESTART,
        payload=None,
        sent_by=current_user.id,
    )


@router.post(
    "/{device_uuid}/update",
    response_model=DeviceCommandResponse,
    status_code=201,
)
async def update_device(
    device_uuid: uuid.UUID,
    image: str = Query(..., description="Docker image tag to deploy"),
    current_user: User = Depends(get_current_user),
    service: DeviceCommandService = Depends(get_command_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_UPDATE)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_device_scope(device_uuid, user_location_ids, db)
    return await service.send_command(
        device_uuid=device_uuid,
        command_type=CommandType.UPDATE,
        payload=f'{{"image": "{image}"}}',
        sent_by=current_user.id,
    )


@router.post(
    "/{device_uuid}/snapshot",
    response_model=DeviceCommandResponse,
    status_code=201,
)
async def request_snapshot(
    device_uuid: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DeviceCommandService = Depends(get_command_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_device_scope(device_uuid, user_location_ids, db)
    return await service.send_command(
        device_uuid=device_uuid,
        command_type=CommandType.SNAPSHOT,
        payload=None,
        sent_by=current_user.id,
    )


@router.get("/status/{command_id}", response_model=DeviceCommandResponse)
async def get_command_status(
    command_id: uuid.UUID,
    service: DeviceCommandService = Depends(get_command_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
):
    return await service.get_command(command_id)


@router.get(
    "/{device_uuid}/history",
    response_model=List[DeviceCommandResponse],
)
async def get_device_command_history(
    device_uuid: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    service: DeviceCommandService = Depends(get_command_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_device_scope(device_uuid, user_location_ids, db)
    return await service.get_device_commands(device_uuid, limit=limit)


@router.get("", response_model=PaginatedResponse[DeviceCommandResponse])
async def list_commands(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    device_id: uuid.UUID = Query(None),
    command_type: CommandType = Query(None),
    service: DeviceCommandService = Depends(get_command_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if device_id:
        filters["device_id"] = device_id
    if command_type:
        filters["command_type"] = command_type
    items = await service.get_all(skip=skip, limit=limit, filters=filters or None)
    total = await service.count(filters=filters or None)
    return build_paginated_response(items, total, page, limit)
