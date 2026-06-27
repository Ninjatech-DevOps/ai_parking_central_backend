"""Celery task: Sync ANPR camera config from edge devices."""

import asyncio
import logging
import uuid

from sqlalchemy import select

from src.celery_app import celery_app
from src.app.db.session import get_celery_session_factory
from src.app.models.anpr_camera_config import AnprCameraConfig
from src.app.models.camera import Camera
from src.app.models.device import Device

logger = logging.getLogger("ai_parking.tasks.anpr_sync")


async def _process(device_id_str: str, payload: dict):
    async with get_celery_session_factory()() as db:
        try:
            result = await db.execute(
                select(Device).where(Device.device_id == device_id_str)
            )
            device = result.scalars().first()
            if not device:
                logger.warning("Unknown device for ANPR sync: %s", device_id_str)
                return

            action = payload.get("action", "upsert")
            camera_id_str = payload.get("camera_id")
            if not camera_id_str:
                logger.warning("No camera_id in ANPR config sync from %s", device_id_str)
                return

            camera_id = uuid.UUID(camera_id_str)

            if action == "delete":
                result = await db.execute(
                    select(AnprCameraConfig).where(AnprCameraConfig.camera_id == camera_id)
                )
                config = result.scalars().first()
                if config:
                    await db.delete(config)
                    await db.commit()
                    logger.info("Deleted ANPR config for camera %s", camera_id)
                return

            # Upsert
            result = await db.execute(
                select(AnprCameraConfig).where(AnprCameraConfig.camera_id == camera_id)
            )
            config = result.scalars().first()

            roi_coords = payload.get("roi_coords")
            trigger_line = payload.get("trigger_line")
            direction = payload.get("direction", "IN")

            if config:
                config.roi_coords = roi_coords
                config.trigger_line = trigger_line
                config.direction = direction
            else:
                config = AnprCameraConfig(
                    camera_id=camera_id,
                    roi_coords=roi_coords,
                    trigger_line=trigger_line,
                    direction=direction,
                )
                db.add(config)

            await db.commit()
            logger.info("ANPR config synced for camera %s from %s", camera_id, device_id_str)

        except Exception:
            await db.rollback()
            logger.exception("Failed to sync ANPR config from %s", device_id_str)
            raise


@celery_app.task(name="tasks.process_anpr_config_sync", bind=True, max_retries=3)
def process_anpr_config_sync(self, device_id: str, payload: dict):
    try:
        asyncio.run(_process(device_id, payload))
    except Exception as exc:
        logger.error("ANPR config sync task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
