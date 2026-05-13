"""Celery task: Process device online/offline status from /status topic + LWT."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.app.core.constants import DeviceStatus
from src.app.db.session import get_celery_session_factory
from src.app.models.device import Device

logger = logging.getLogger("ai_parking.tasks.device_status")

_STATUS_MAP = {
    "online": DeviceStatus.ONLINE,
    "offline": DeviceStatus.OFFLINE,
}


async def _process(device_id_str: str, status: str):
    async with get_celery_session_factory()() as db:
        try:
            result = await db.execute(
                select(Device).where(Device.device_id == device_id_str)
            )
            device = result.scalars().first()
            if not device:
                logger.warning("Status from unknown device: %s", device_id_str)
                return

            new_status = _STATUS_MAP.get(status.lower())
            if not new_status:
                logger.warning("Unknown status value '%s' from device %s", status, device_id_str)
                return

            values = {"status": new_status, "last_seen": datetime.now(timezone.utc)}

            await db.execute(
                update(Device).where(Device.id == device.id).values(**values)
            )
            await db.commit()
            logger.info("Device %s → %s", device_id_str, new_status.value)

        except Exception:
            await db.rollback()
            logger.exception("Failed to process status for %s", device_id_str)
            raise


@celery_app.task(name="tasks.process_device_status", bind=True, max_retries=3)
def process_device_status(self, device_id: str, status: str):
    try:
        asyncio.run(_process(device_id, status))
    except Exception as exc:
        logger.error("Device status task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
