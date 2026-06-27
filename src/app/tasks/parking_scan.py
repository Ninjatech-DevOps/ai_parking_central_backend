"""Celery task: Create a ParkingScan record from slot snapshot data."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func

from src.celery_app import celery_app
from src.app.core.constants import SlotState, SlotType
from src.app.db.session import get_celery_session_factory
from src.app.models.camera import Camera
from src.app.models.device import Device
from src.app.models.parking_scan import ParkingScan
from src.app.models.parking_slot import ParkingSlot

logger = logging.getLogger("ai_parking.tasks.parking_scan")


async def _process(device_id_str: str, camera_id: str, image_url: str):
    async with get_celery_session_factory()() as db:
        try:
            # Resolve device
            result = await db.execute(
                select(Device).where(Device.device_id == device_id_str)
            )
            device = result.scalars().first()
            if not device:
                return

            # Resolve camera
            cam_result = await db.execute(
                select(Camera).where(
                    Camera.device_id == device.id,
                    Camera.position_label == camera_id,
                ) if not _is_uuid(camera_id) else
                select(Camera).where(Camera.id == uuid.UUID(camera_id))
            )
            camera = cam_result.scalars().first()
            if not camera:
                return

            # Count slots by state for this camera
            slots_result = await db.execute(
                select(ParkingSlot).where(
                    ParkingSlot.camera_id == camera.id,
                    ParkingSlot.is_active == True,
                )
            )
            slots = list(slots_result.scalars().all())

            car_occupied = 0
            car_total = 0
            tw_occupied = 0
            tw_total = 0
            has_obstruction = False

            for slot in slots:
                car_cap = slot.capacity_car or (1 if slot.slot_type == SlotType.CAR.value else 0)
                tw_cap = slot.capacity_two_wheeler or (1 if slot.slot_type == SlotType.TWO_WHEELER.value else 0)

                if slot.slot_type == SlotType.GENERAL.value and car_cap == 0 and tw_cap == 0:
                    car_cap = 1  # Default general slot as 1 car

                car_total += car_cap
                tw_total += tw_cap
                car_occupied += slot.occupied_car
                tw_occupied += slot.occupied_two_wheeler

                if slot.state == SlotState.VEHICLE and slot.occupied_car == 0 and slot.occupied_two_wheeler == 0:
                    # Single-capacity slot with vehicle
                    if slot.detected_vehicle_type == "TWO_WHEELER":
                        tw_occupied += 1
                    else:
                        car_occupied += 1

                if slot.state == SlotState.OBSTRUCTED:
                    has_obstruction = True

            scan = ParkingScan(
                device_id=device.id,
                camera_id=camera.id,
                location_id=device.location_id,
                city_id=device.city_id,
                image_url=image_url,
                car_occupied=car_occupied,
                car_available=max(0, car_total - car_occupied),
                car_total=car_total,
                two_wheeler_occupied=tw_occupied,
                two_wheeler_available=max(0, tw_total - tw_occupied),
                two_wheeler_total=tw_total,
                has_obstruction=has_obstruction,
            )
            db.add(scan)
            await db.commit()
            logger.info("ParkingScan created for %s camera=%s", device_id_str, camera_id)

        except Exception:
            await db.rollback()
            logger.exception("Failed to create ParkingScan for %s", device_id_str)
            raise


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


@celery_app.task(name="tasks.create_parking_scan", bind=True, max_retries=2)
def create_parking_scan(self, device_id: str, camera_id: str, image_url: str = ""):
    try:
        asyncio.run(_process(device_id, camera_id, image_url))
    except Exception as exc:
        logger.error("ParkingScan task failed, retrying: %s", exc)
        self.retry(countdown=3, exc=exc)
