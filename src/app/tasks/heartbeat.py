"""Celery task: Process device heartbeat — update status, store telemetry."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.app.core.constants import DeviceStatus, CameraStatus
from src.app.db.session import get_celery_session_factory
from src.app.models.device import Device
from src.app.models.camera import Camera
from src.app.models.device_telemetry import DeviceTelemetry

logger = logging.getLogger("ai_parking.tasks.heartbeat")


async def _process(device_id_str: str, data: dict):
    async with get_celery_session_factory()() as db:
        try:
            result = await db.execute(
                select(Device).where(Device.device_id == device_id_str)
            )
            device = result.scalars().first()
            if not device:
                logger.warning("Heartbeat from unknown device: %s", device_id_str)
                return

            now = datetime.now(timezone.utc)

            # Update device status and last_seen
            await db.execute(
                update(Device)
                .where(Device.id == device.id)
                .values(status=DeviceStatus.ONLINE, last_seen=now)
            )

            # Store telemetry
            telemetry = DeviceTelemetry(
                device_id=device.id,
                cpu_percent=data.get("cpu_percent"),
                temperature=data.get("temperature"),
                memory_percent=data.get("memory_percent"),
                disk_percent=data.get("disk_percent"),
                uptime_seconds=data.get("uptime_seconds"),
            )
            db.add(telemetry)

            # Update camera statuses if provided
            for cam_data in data.get("cameras", []):
                cam_id = cam_data.get("id")
                cam_status = cam_data.get("status", "ACTIVE").upper()
                if cam_id and cam_status in [s.value for s in CameraStatus]:
                    result = await db.execute(
                        select(Camera).where(
                            Camera.device_id == device.id,
                            Camera.position_label == cam_id,
                        )
                    )
                    camera = result.scalars().first()
                    if camera:
                        await db.execute(
                            update(Camera)
                            .where(Camera.id == camera.id)
                            .values(status=CameraStatus(cam_status))
                        )

            await db.commit()
            logger.debug("Heartbeat processed for %s", device_id_str)

        except Exception:
            await db.rollback()
            logger.exception("Failed to process heartbeat for %s", device_id_str)
            raise


@celery_app.task(name="tasks.process_heartbeat", bind=True, max_retries=3)
def process_heartbeat(self, device_id: str, data: dict):
    try:
        asyncio.run(_process(device_id, data))
    except Exception as exc:
        logger.error("Heartbeat task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
