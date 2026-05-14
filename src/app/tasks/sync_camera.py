"""Celery task: Sync camera config from edge device via MQTT."""

import asyncio
import logging

from src.celery_app import celery_app
from src.app.db.session import get_celery_session_factory
from src.app.repositories.device import DeviceRepository
from src.app.repositories.camera import CameraRepository
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.services.device_sync import DeviceSyncService

logger = logging.getLogger("ai_parking.tasks.sync_camera")


async def _process(device_id: str, action: str, camera_data: dict):
    async with get_celery_session_factory()() as db:
        service = DeviceSyncService(
            DeviceRepository(db), CameraRepository(db), ParkingSlotRepository(db),
        )
        await service.sync_camera(device_id, action, camera_data)
        await db.commit()


@celery_app.task(name="tasks.process_sync_camera", bind=True, max_retries=3)
def process_sync_camera(self, device_id: str, action: str, camera_data: dict):
    try:
        asyncio.run(_process(device_id, action, camera_data))
    except Exception as exc:
        logger.error("Sync camera task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)


async def _update_snapshot(device_id_str: str, camera_label: str, path: str, width: int, height: int):
    async with get_celery_session_factory()() as db:
        device_repo = DeviceRepository(db)
        camera_repo = CameraRepository(db)

        device = await device_repo.get_by_device_id(device_id_str)
        if not device:
            return

        camera = await camera_repo.get_by_device_and_label(device.id, camera_label)
        if not camera:
            return

        await camera_repo.update(camera.id, {
            "frame_width": width,
            "frame_height": height,
            "snapshot_path": path,
        })
        await db.commit()
        logger.info("Camera '%s' snapshot updated: %dx%d", camera_label, width, height)


@celery_app.task(name="tasks.update_camera_snapshot")
def update_camera_snapshot(device_id: str, camera_label: str, path: str, width: int, height: int):
    asyncio.run(_update_snapshot(device_id, camera_label, path, width, height))
