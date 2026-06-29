"""Celery task: Process ANPR records from edge devices."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from src.celery_app import celery_app
from src.app.core.constants import AnprDirection, VehicleType
from src.app.db.session import get_celery_session_factory
from src.app.models.anpr_record import AnprRecord
from src.app.models.anpr_session import AnprSession
from src.app.models.camera import Camera
from src.app.models.device import Device

logger = logging.getLogger("ai_parking.tasks.anpr_record")


async def _process(device_id_str: str, payload: dict):
    async with get_celery_session_factory()() as db:
        try:
            # Resolve device
            result = await db.execute(
                select(Device).where(Device.device_id == device_id_str)
            )
            device = result.scalars().first()
            if not device:
                logger.warning("Unknown device for ANPR: %s", device_id_str)
                return

            # Resolve camera by label or ID
            camera_label = payload.get("camera_label")
            camera_id_str = payload.get("camera_id")
            camera = None
            if camera_id_str:
                result = await db.execute(
                    select(Camera).where(Camera.id == uuid.UUID(camera_id_str))
                )
                camera = result.scalars().first()
            elif camera_label:
                result = await db.execute(
                    select(Camera).where(
                        Camera.device_id == device.id,
                        Camera.position_label == camera_label,
                    )
                )
                camera = result.scalars().first()

            if not camera:
                logger.warning("Camera not found for ANPR record from %s", device_id_str)
                return

            number_plate = payload.get("number_plate", "").strip().upper()
            if not number_plate:
                logger.warning("Empty number plate from %s", device_id_str)
                return

            raw_vtype = payload.get("vehicle_type", "CAR").upper()
            vehicle_type = raw_vtype if raw_vtype in [v.value for v in VehicleType] else VehicleType.CAR

            raw_direction = payload.get("direction", "IN").upper()
            direction = raw_direction if raw_direction in [d.value for d in AnprDirection] else AnprDirection.IN

            image_url = payload.get("image_url")
            gemini_result = payload.get("gemini_result")
            paddle_result = payload.get("paddle_result")
            confidence_gemini = payload.get("confidence_gemini")
            confidence_paddle = payload.get("confidence_paddle")

            recorded_at_str = payload.get("recorded_at")
            recorded_at = (
                datetime.fromisoformat(recorded_at_str) if recorded_at_str
                else datetime.now(timezone.utc)
            )

            # Create ANPR record
            record = AnprRecord(
                device_id=device.id,
                camera_id=camera.id,
                location_id=device.location_id,
                city_id=device.city_id,
                number_plate=number_plate,
                vehicle_type=vehicle_type,
                direction=direction,
                image_url=image_url,
                gemini_result=gemini_result,
                paddle_result=paddle_result,
                confidence_gemini=confidence_gemini,
                confidence_paddle=confidence_paddle,
                recorded_at=recorded_at,
            )
            db.add(record)
            await db.flush()

            # Session matching
            if direction == AnprDirection.IN:
                # Create new session
                session = AnprSession(
                    location_id=device.location_id,
                    city_id=device.city_id,
                    number_plate=number_plate,
                    vehicle_type=vehicle_type,
                    entry_record_id=record.id,
                    entry_time=recorded_at,
                    entry_image_url=image_url,
                    is_active=True,
                )
                db.add(session)
                logger.info("ANPR IN: %s at %s (device=%s)", number_plate, device.location_id, device_id_str)

            elif direction == AnprDirection.OUT:
                # Find active session with same plate at same location
                result = await db.execute(
                    select(AnprSession).where(
                        AnprSession.location_id == device.location_id,
                        AnprSession.number_plate == number_plate,
                        AnprSession.is_active == True,
                    ).order_by(AnprSession.entry_time.desc()).limit(1)
                )
                session = result.scalars().first()
                if session:
                    session.exit_record_id = record.id
                    session.exit_time = recorded_at
                    session.exit_image_url = image_url
                    session.is_active = False
                    logger.info("ANPR OUT: %s matched session at %s", number_plate, device.location_id)
                else:
                    logger.warning("ANPR OUT: No active session for %s at %s", number_plate, device.location_id)

            await db.commit()
            logger.info("ANPR record processed: %s %s %s", number_plate, direction, device_id_str)

            # Publish ACK so the edge device can map its local_id → central record id
            local_id = payload.get("local_id")
            if local_id is not None:
                _publish_ack(device_id_str, local_id, str(record.id))

        except Exception:
            await db.rollback()
            logger.exception("Failed to process ANPR record from %s", device_id_str)
            raise


def _publish_ack(device_id_str: str, local_id: int, central_id: str) -> None:
    """Publish ACK back to edge device so it can store the central_detection_id."""
    try:
        from src.app.core.constants import MQTTTopics
        from src.app.mqtt.client import get_mqtt_client

        topic = MQTTTopics.ANPR_ACK.format(device_id=device_id_str)
        client = get_mqtt_client()
        if client:
            import json
            payload = json.dumps({
                "type": "detection_ack",
                "local_id": local_id,
                "central_id": central_id,
            })
            client.publish(topic, payload, qos=1)
            logger.info("ANPR ACK sent to %s: local_id=%s → central_id=%s", device_id_str, local_id, central_id)
    except Exception:
        logger.exception("Failed to publish ANPR ACK to %s", device_id_str)


@celery_app.task(name="tasks.process_anpr_record", bind=True, max_retries=3)
def process_anpr_record(self, device_id: str, payload: dict):
    try:
        asyncio.run(_process(device_id, payload))
    except Exception as exc:
        logger.error("ANPR record task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
