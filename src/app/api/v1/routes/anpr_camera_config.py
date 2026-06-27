import uuid
from typing import Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids
from src.app.core.constants import MQTTTopics, Permission
from src.app.db.session import get_db
from src.app.mqtt.client import publish_command
from src.app.repositories.anpr_camera_config import AnprCameraConfigRepository
from src.app.schemas.anpr_camera_config import (
    AnprCameraConfigCreate,
    AnprCameraConfigResponse,
    AnprCameraConfigUpdate,
)
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.services.anpr_camera_config import AnprCameraConfigService
from src.app.utils.pagination import build_paginated_response, get_pagination_params

router = APIRouter(prefix="/anpr-configs", tags=["ANPR Camera Config"])


def _get_service(db: AsyncSession = Depends(get_db)) -> AnprCameraConfigService:
    return AnprCameraConfigService(AnprCameraConfigRepository(db))


@router.get("", response_model=PaginatedResponse[AnprCameraConfigResponse])
async def list_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    camera_id: Optional[uuid.UUID] = Query(None),
    service: AnprCameraConfigService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {}
    if camera_id:
        filters["camera_id"] = camera_id
    items = await service.get_all(skip, limit, filters)
    total = await service.count(filters)
    return build_paginated_response(items, total, page, limit)


@router.get("/{config_id}", response_model=AnprCameraConfigResponse)
async def get_config(
    config_id: uuid.UUID,
    service: AnprCameraConfigService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_VIEW)),
):
    return await service.get_by_id(config_id)


@router.get("/camera/{camera_id}", response_model=Optional[AnprCameraConfigResponse])
async def get_config_by_camera(
    camera_id: uuid.UUID,
    service: AnprCameraConfigService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_VIEW)),
):
    return await service.get_by_camera_id(camera_id)


@router.post("", response_model=AnprCameraConfigResponse, status_code=201)
async def create_config(
    data: AnprCameraConfigCreate,
    service: AnprCameraConfigService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_CONFIGURE)),
    db: AsyncSession = Depends(get_db),
):
    config = await service.create(data.model_dump())
    # Publish config to client device via MQTT
    _publish_config_to_device(db, config)
    return config


@router.patch("/{config_id}", response_model=AnprCameraConfigResponse)
async def update_config(
    config_id: uuid.UUID,
    data: AnprCameraConfigUpdate,
    service: AnprCameraConfigService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_CONFIGURE)),
    db: AsyncSession = Depends(get_db),
):
    config = await service.update(config_id, data.model_dump(exclude_unset=True))
    _publish_config_to_device(db, config)
    return config


@router.delete("/{config_id}", response_model=MessageResponse)
async def delete_config(
    config_id: uuid.UUID,
    service: AnprCameraConfigService = Depends(_get_service),
    _: bool = Depends(PermissionChecker(Permission.ANPR_CONFIGURE)),
):
    await service.delete(config_id)
    return MessageResponse(message="ANPR config deleted")


def _publish_config_to_device(db, config):
    """Best-effort publish config sync to device."""
    try:
        if config.camera and config.camera.device:
            device_id = config.camera.device.device_id
            publish_command(device_id, MQTTTopics.ANPR_CMD_CONFIG, {
                "action": "upsert",
                "camera_id": str(config.camera_id),
                "roi_coords": config.roi_coords,
                "trigger_line": config.trigger_line,
                "direction": config.direction.value if hasattr(config.direction, "value") else config.direction,
            })
    except Exception:
        pass
