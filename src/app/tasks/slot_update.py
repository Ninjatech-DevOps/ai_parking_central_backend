"""Celery task: Process slot state changes from edge devices."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.app.core.constants import DeviceStatus, SlotState, VehicleType
from src.app.db.session import get_celery_session_factory
from src.app.models.device import Device
from src.app.models.parking_slot import ParkingSlot
from src.app.models.slot_event import SlotEvent

logger = logging.getLogger("ai_parking.tasks.slot_update")


async def _process(device_id_str: str, slots: list):
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

            updated_count = 0
            for slot_data in slots:
                slot_label = slot_data.get("slot_label")
                new_state_str = slot_data.get("state", "").upper()

                if new_state_str not in [s.value for s in SlotState]:
                    logger.warning("Invalid slot state: %s", new_state_str)
                    continue

                new_state = SlotState(new_state_str)

                # Extract vehicle type (nullable, validated)
                raw_vtype = slot_data.get("detected_vehicle_type")
                detected_vtype = raw_vtype if raw_vtype in [v.value for v in VehicleType] else None
                effective_vtype = detected_vtype if new_state == SlotState.VEHICLE else None
                is_mismatched = slot_data.get("is_mismatched", False)

                # Find active slot by label within device's zone
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

                if slot.state == new_state and slot.detected_vehicle_type == effective_vtype:
                    continue

                previous_state = slot.state

                await db.execute(
                    update(ParkingSlot)
                    .where(ParkingSlot.id == slot.id)
                    .values(state=new_state, detected_vehicle_type=effective_vtype)
                )

                event = SlotEvent(
                    parking_slot_id=slot.id,
                    previous_state=previous_state,
                    new_state=new_state,
                    device_id=device.id,
                    detected_vehicle_type=effective_vtype,
                    is_mismatched=is_mismatched,
                )
                db.add(event)
                updated_count += 1

            await db.commit()
            if updated_count > 0:
                logger.info("Device %s: updated %d slot(s)", device_id_str, updated_count)

        except Exception:
            await db.rollback()
            logger.exception("Failed to process slot update for %s", device_id_str)
            raise


@celery_app.task(name="tasks.process_slot_update", bind=True, max_retries=3)
def process_slot_update(self, device_id: str, slots: list):
    try:
        asyncio.run(_process(device_id, slots))
    except Exception as exc:
        logger.error("Slot update task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
