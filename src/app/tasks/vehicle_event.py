"""Celery task: Process vehicle entry/exit events from multi-capacity zones."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.app.core.constants import DeviceStatus, SlotState, VehicleType
from src.app.db.session import get_celery_session_factory
from src.app.models.device import Device
from src.app.models.parking_slot import ParkingSlot
from src.app.models.slot_event import SlotEvent

logger = logging.getLogger("ai_parking.tasks.vehicle_event")


async def _process(device_id_str: str, camera_id: Optional[str], events: list):
    async with get_celery_session_factory()() as db:
        try:
            result = await db.execute(
                select(Device).where(Device.device_id == device_id_str)
            )
            device = result.scalars().first()
            if not device:
                logger.warning("Unknown device: %s", device_id_str)
                return

            # Mark device as online
            await db.execute(
                update(Device)
                .where(Device.id == device.id)
                .values(status=DeviceStatus.ONLINE, last_seen=datetime.now(timezone.utc))
            )

            processed = 0
            for evt in events:
                slot_label = evt.get("slot_label")
                event_type = evt.get("event_type")  # ENTERED or EXITED
                vehicle_type_str = evt.get("vehicle_type")
                image_url = evt.get("image_url")
                track_id = evt.get("track_id")
                duration = evt.get("duration_seconds")

                if event_type not in ("ENTERED", "EXITED"):
                    continue

                # Find slot
                query = select(ParkingSlot).where(
                    ParkingSlot.label == slot_label,
                    ParkingSlot.is_active == True,
                )
                if device.zone_id:
                    query = query.where(ParkingSlot.zone_id == device.zone_id)
                result = await db.execute(query)
                slot = result.scalars().first()

                if not slot:
                    logger.warning("Slot %s not found for device %s", slot_label, device_id_str)
                    continue

                # Map event_type to SlotState for slot_events table
                if event_type == "ENTERED":
                    new_state = SlotState.VEHICLE
                    previous_state = SlotState.EMPTY
                else:
                    new_state = SlotState.EMPTY
                    previous_state = SlotState.VEHICLE

                detected_vtype = vehicle_type_str if vehicle_type_str in [v.value for v in VehicleType] else None

                event = SlotEvent(
                    parking_slot_id=slot.id,
                    previous_state=previous_state,
                    new_state=new_state,
                    device_id=device.id,
                    detected_vehicle_type=detected_vtype,
                    is_mismatched=False,
                    image_url=image_url,
                )
                db.add(event)
                processed += 1

            await db.commit()
            if processed > 0:
                logger.info(
                    "Device %s: %d vehicle event(s) processed (camera=%s)",
                    device_id_str, processed, camera_id,
                )

        except Exception:
            await db.rollback()
            logger.exception("Failed to process vehicle events for %s", device_id_str)
            raise


@celery_app.task(name="tasks.process_vehicle_events", bind=True, max_retries=3)
def process_vehicle_events(self, device_id: str, camera_id: Optional[str], events: list):
    try:
        asyncio.run(_process(device_id, camera_id, events))
    except Exception as exc:
        logger.error("Vehicle event task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
