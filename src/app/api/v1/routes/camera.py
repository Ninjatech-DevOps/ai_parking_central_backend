import logging
import os
import uuid
from typing import List, Optional, Set

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker, get_user_location_ids, verify_location_in_scope
from src.app.core.constants import CameraModuleType, MQTTTopics, Permission
from src.app.db.session import get_db
from src.app.mqtt.client import publish_command
from src.app.repositories.camera import CameraRepository
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.schemas.base import MessageResponse, PaginatedResponse
from src.app.schemas.camera import (
    CameraCreate, CameraResponse, CameraUpdate, SlotConfigRequest,
)
from src.app.services.camera import CameraService
from src.app.services.device_config_push import push_camera_config, push_calibrate
from src.app.repositories.device import DeviceRepository
from src.app.utils.pagination import build_paginated_response, get_pagination_params

logger = logging.getLogger("ai_parking.routes.camera")

router = APIRouter(prefix="/cameras", tags=["Cameras"])


async def _verify_camera_scope(
    camera_id: uuid.UUID,
    user_location_ids: Optional[Set[uuid.UUID]],
    db: AsyncSession,
) -> None:
    """Resolve camera → device → location_id, then check scope."""
    cam = await CameraRepository(db).get_by_id(camera_id)
    if not cam:
        return  # service.get() will raise NotFoundException
    device = await DeviceRepository(db).get_by_id(cam.device_id)
    if device:
        verify_location_in_scope(device.location_id, user_location_ids)


def get_camera_service(db: AsyncSession = Depends(get_db)) -> CameraService:
    return CameraService(
        camera_repo=CameraRepository(db),
        slot_repo=ParkingSlotRepository(db),
    )


@router.post("", response_model=CameraResponse, status_code=201,
    dependencies=[Depends(PermissionChecker(Permission.DEVICES_CREATE))])
async def create_camera(
    body: CameraCreate,
    service: CameraService = Depends(get_camera_service),
    db: AsyncSession = Depends(get_db),
):
    camera = await service.create(body.model_dump())
    # Push to edge device via MQTT
    device = await DeviceRepository(db).get_by_id(camera.device_id)
    if device:
        if camera.module_type == CameraModuleType.ANPR:
            payload = {
                "action": "CREATE",
                "camera_id": str(camera.id),
                "name": camera.position_label,
                "stream_url": camera.source or "",
                "direction": "IN",
                "is_active": True,
            }
            topic = MQTTTopics.ANPR_CMD_CONFIG.format(device_id=device.device_id)
            publish_command(device.device_id, MQTTTopics.ANPR_CMD_CONFIG, payload)
            logger.info("ANPR camera CREATE published to %s: camera_id=%s name=%s", topic, camera.id, camera.position_label)
        else:
            push_camera_config(device.device_id, "create", {
                "label": camera.position_label,
                "source": camera.source or "0",
                "camera_type": camera.camera_type.value if hasattr(camera.camera_type, "value") else str(camera.camera_type or "USB"),
            })
            logger.info("AI Parking camera CREATE pushed to %s: label=%s", device.device_id, camera.position_label)
    return camera


@router.get("", response_model=PaginatedResponse[CameraResponse])
async def list_cameras(
    page: int = Query(1, ge=1),
    page_size: int = Query(None),
    device_id: uuid.UUID = Query(None),
    service: CameraService = Depends(get_camera_service),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
):
    skip, limit = get_pagination_params(page, page_size)
    filters = {"is_active": True}
    if device_id: filters["device_id"] = device_id
    items = await service.get_all(skip=skip, limit=limit, filters=filters)
    total = await service.count(filters=filters)
    return build_paginated_response(items, total, page, limit)


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: uuid.UUID,
    service: CameraService = Depends(get_camera_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_camera_scope(camera_id, user_location_ids, db)
    return await service.get(camera_id)


@router.patch("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: uuid.UUID,
    body: CameraUpdate,
    service: CameraService = Depends(get_camera_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_EDIT)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_camera_scope(camera_id, user_location_ids, db)
    camera = await service.update(camera_id, body.model_dump(exclude_unset=True))
    # Push update to edge device
    device = await DeviceRepository(db).get_by_id(camera.device_id)
    if device and camera.module_type == CameraModuleType.ANPR:
        payload = {
            "action": "UPDATE",
            "camera_id": str(camera.id),
            "name": camera.position_label,
            "stream_url": camera.source or "",
            "is_active": camera.is_active,
        }
        publish_command(device.device_id, MQTTTopics.ANPR_CMD_CONFIG, payload)
        logger.info("ANPR camera UPDATE published to %s: camera_id=%s", device.device_id, camera.id)
    return camera


@router.delete("/{camera_id}", response_model=MessageResponse)
async def delete_camera(
    camera_id: uuid.UUID,
    service: CameraService = Depends(get_camera_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_DELETE)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    await _verify_camera_scope(camera_id, user_location_ids, db)
    camera = await service.get(camera_id)
    device = await DeviceRepository(db).get_by_id(camera.device_id)
    await service.delete(camera_id)
    if device:
        if camera.module_type == CameraModuleType.ANPR:
            payload = {
                "action": "DELETE",
                "camera_id": str(camera.id),
            }
            publish_command(device.device_id, MQTTTopics.ANPR_CMD_CONFIG, payload)
            logger.info("ANPR camera DELETE published to %s: camera_id=%s", device.device_id, camera.id)
        else:
            push_camera_config(device.device_id, "delete", {"label": camera.position_label})
            logger.info("AI Parking camera DELETE pushed to %s: label=%s", device.device_id, camera.position_label)
    return MessageResponse(message="Camera deleted successfully")


@router.post("/{camera_id}/slot-config", response_model=CameraResponse)
async def apply_slot_config(
    camera_id: uuid.UUID,
    body: SlotConfigRequest,
    service: CameraService = Depends(get_camera_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_UPDATE)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Client pushes slot position config for a camera."""
    await _verify_camera_scope(camera_id, user_location_ids, db)
    return await service.apply_slot_config(
        camera_id, [s.model_dump() for s in body.slots]
    )


@router.get("/{camera_id}/snapshot")
async def get_camera_snapshot(
    camera_id: uuid.UUID,
    service: CameraService = Depends(get_camera_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_VIEW)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Get the reference snapshot for a camera — always fresh, never cached."""
    await _verify_camera_scope(camera_id, user_location_ids, db)
    from fastapi.responses import Response
    camera = await service.get(camera_id)
    if camera.snapshot_path and os.path.exists(camera.snapshot_path):
        with open(camera.snapshot_path, "rb") as f:
            data = f.read()
        return Response(
            content=data,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    from src.app.exceptions.base import NotFoundException
    raise NotFoundException(detail="No snapshot available. Capture one first.")


@router.post("/{camera_id}/capture-snapshot", response_model=MessageResponse)
async def capture_camera_snapshot(
    camera_id: uuid.UUID,
    service: CameraService = Depends(get_camera_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_UPDATE)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Send snapshot command to edge device for this camera."""
    await _verify_camera_scope(camera_id, user_location_ids, db)
    from src.app.mqtt.client import publish_command
    from src.app.core.constants import MQTTTopics

    camera = await service.get(camera_id)
    device = await DeviceRepository(db).get_by_id(camera.device_id)
    if not device:
        from src.app.exceptions.base import NotFoundException
        raise NotFoundException(detail="Device not found")

    publish_command(device.device_id, MQTTTopics.CMD_SNAPSHOT, {
        "command_id": str(uuid.uuid4()),
        "action": "SNAPSHOT",
        "payload": {"camera_label": camera.position_label},
    })
    return MessageResponse(message="Snapshot command sent")


@router.post("/{camera_id}/slots/{slot_id}/calibrate")
async def calibrate_slot(
    camera_id: uuid.UUID,
    slot_id: uuid.UUID,
    service: CameraService = Depends(get_camera_service),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.DEVICES_UPDATE)),
    user_location_ids: Optional[Set[uuid.UUID]] = Depends(get_user_location_ids),
):
    """Send calibrate command to edge device for a specific slot."""
    await _verify_camera_scope(camera_id, user_location_ids, db)
    camera = await service.get(camera_id)
    device = await DeviceRepository(db).get_by_id(camera.device_id)
    if not device:
        from src.app.exceptions.base import NotFoundException
        raise NotFoundException(detail="Device not found")

    slot_repo = ParkingSlotRepository(db)
    slot = await slot_repo.get_by_id(slot_id)
    if not slot:
        from src.app.exceptions.base import NotFoundException
        raise NotFoundException(detail="Slot not found")

    from src.app.models.device_command import DeviceCommand
    from src.app.core.constants import CommandType, CommandStatus
    import json as _json

    command = DeviceCommand(
        device_id=device.id,
        command_type=CommandType.SNAPSHOT,  # reuse type for now
        payload=_json.dumps({"camera_label": camera.position_label, "slot_label": slot.label}),
        status=CommandStatus.SENT,
    )
    db.add(command)
    await db.flush()

    from src.app.mqtt.client import publish_command
    from src.app.core.constants import MQTTTopics
    publish_command(device.device_id, MQTTTopics.CMD_CALIBRATE, {
        "command_id": str(command.id),
        "action": "calibrate",
        "payload": {
            "camera_label": camera.position_label,
            "slot_label": slot.label,
        },
    })
    await db.commit()

    return {"message": f"Calibrate command sent for slot {slot.label}", "command_id": str(command.id)}
