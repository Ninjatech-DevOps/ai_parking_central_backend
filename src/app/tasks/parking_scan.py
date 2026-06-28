"""Celery task: Create a ParkingScan record from client-published scan data."""

import asyncio
import logging
import uuid

from sqlalchemy import select

from src.celery_app import celery_app
from src.app.db.session import get_celery_session_factory
from src.app.models.camera import Camera
from src.app.models.device import Device
from src.app.models.parking_scan import ParkingScan

logger = logging.getLogger("ai_parking.tasks.parking_scan")


async def _process(device_id_str: str, payload: dict):
    """Create ParkingScan directly from client payload — no re-computation needed."""
    async with get_celery_session_factory()() as db:
        try:
            result = await db.execute(
                select(Device).where(Device.device_id == device_id_str)
            )
            device = result.scalars().first()
            if not device:
                logger.warning("Unknown device for parking scan: %s", device_id_str)
                return

            # Resolve camera by label
            camera_label = payload.get("camera_label", "")
            camera = None
            if camera_label:
                cam_result = await db.execute(
                    select(Camera).where(
                        Camera.device_id == device.id,
                        Camera.position_label == camera_label,
                    )
                )
                camera = cam_result.scalars().first()

            if not camera:
                # Fallback: pick first camera on this device
                cam_result = await db.execute(
                    select(Camera).where(Camera.device_id == device.id).limit(1)
                )
                camera = cam_result.scalars().first()

            if not camera:
                logger.warning("No camera found for parking scan from %s", device_id_str)
                return

            scan = ParkingScan(
                device_id=device.id,
                camera_id=camera.id,
                location_id=device.location_id,
                city_id=device.city_id,
                image_url=payload.get("image_url", ""),
                car_occupied=payload.get("car_occupied", 0),
                car_available=payload.get("car_available", 0),
                car_total=payload.get("car_total", 0),
                two_wheeler_occupied=payload.get("two_wheeler_occupied", 0),
                two_wheeler_available=payload.get("two_wheeler_available", 0),
                two_wheeler_total=payload.get("two_wheeler_total", 0),
                has_obstruction=payload.get("has_obstruction", False),
            )
            db.add(scan)
            await db.commit()
            logger.info("ParkingScan created for %s camera=%s", device_id_str, camera_label)

        except Exception:
            await db.rollback()
            logger.exception("Failed to create ParkingScan for %s", device_id_str)
            raise


@celery_app.task(name="tasks.process_parking_scan", bind=True, max_retries=2)
def process_parking_scan(self, device_id: str, payload: dict):
    try:
        asyncio.run(_process(device_id, payload))
    except Exception as exc:
        logger.error("ParkingScan task failed, retrying: %s", exc)
        self.retry(countdown=3, exc=exc)
