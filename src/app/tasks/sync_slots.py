"""Celery task: Sync slots + polygon config from edge device via MQTT."""

import asyncio
import logging

from src.celery_app import celery_app
from src.app.db.session import get_celery_session_factory
from src.app.repositories.device import DeviceRepository
from src.app.repositories.camera import CameraRepository
from src.app.repositories.parking_slot import ParkingSlotRepository
from src.app.services.device_sync import DeviceSyncService

logger = logging.getLogger("ai_parking.tasks.sync_slots")


async def _process(device_id: str, action: str, camera_label: str, slots: list):
    async with get_celery_session_factory()() as db:
        service = DeviceSyncService(
            DeviceRepository(db), CameraRepository(db), ParkingSlotRepository(db),
        )
        await service.sync_slots(device_id, action, camera_label, slots)
        await db.commit()


@celery_app.task(name="tasks.process_sync_slots", bind=True, max_retries=3)
def process_sync_slots(self, device_id: str, action: str, camera_label: str, slots: list):
    try:
        asyncio.run(_process(device_id, action, camera_label, slots))
    except Exception as exc:
        logger.error("Sync slots task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
