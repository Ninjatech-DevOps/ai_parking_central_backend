"""Celery task: Process device heartbeat — update status, store telemetry."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.app.core.constants import (
    DeviceStatus, CameraStatus, AlertSeverity, AlertStatus, AlertTriggerType,
)
from src.app.db.session import get_celery_session_factory
from src.app.models.device import Device
from src.app.models.camera import Camera
from src.app.models.device_telemetry import DeviceTelemetry
from src.app.models.alert_rule import AlertRule
from src.app.models.alert_event import AlertEvent

logger = logging.getLogger("ai_parking.tasks.heartbeat")


async def _process(device_id_str: str, data: dict):
    async with get_celery_session_factory()() as db:
        try:
            # FOR UPDATE (no skip) — second concurrent heartbeat blocks until first commits
            # This prevents duplicate "back online" alerts
            result = await db.execute(
                select(Device)
                .where(Device.device_id == device_id_str)
                .with_for_update()
            )
            device = result.scalars().first()
            if not device:
                logger.warning("Heartbeat from unknown device: %s", device_id_str)
                return

            now = datetime.now(timezone.utc)
            was_offline = device.status == DeviceStatus.OFFLINE

            # Update device status and last_seen FIRST — so blocked concurrent workers
            # will see ONLINE when they acquire the lock
            await db.execute(
                update(Device)
                .where(Device.id == device.id)
                .values(status=DeviceStatus.ONLINE, last_seen=now)
            )

            # Device came back online — resolve offline alert + create online alert
            pending_notification = None
            if was_offline:
                pending_notification = await _handle_device_back_online(db, device, now)

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

            # Dispatch notifications AFTER commit so alert row is visible to notification worker
            if pending_notification:
                from src.app.tasks.notifications import dispatch_alert_notifications
                dispatch_alert_notifications.delay(*pending_notification)

        except Exception:
            await db.rollback()
            logger.exception("Failed to process heartbeat for %s", device_id_str)
            raise


async def _handle_device_back_online(db, device, now):
    """Resolve active DEVICE_OFFLINE alerts and create a DEVICE_ONLINE alert.
    Returns (alert_id, location_id) tuple for post-commit notification dispatch, or None.
    """
    # Auto-resolve any active DEVICE_OFFLINE alerts for this device
    result = await db.execute(
        select(AlertEvent).where(
            AlertEvent.device_id == device.id,
            AlertEvent.status == AlertStatus.ACTIVE,
        )
    )
    for alert in result.scalars().all():
        await db.execute(
            update(AlertEvent)
            .where(AlertEvent.id == alert.id)
            .values(status=AlertStatus.RESOLVED, resolved_at=now)
        )

    # Get DEVICE_ONLINE alert rule
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.trigger_type == AlertTriggerType.DEVICE_ONLINE,
            AlertRule.is_active == True,
        )
    )
    rule = result.scalars().first()
    if not rule:
        logger.warning("No DEVICE_ONLINE alert rule found. Skipping online alert.")
        return None

    # Create "device back online" alert event
    loc_name = device.location.name if device.location else "Unknown"
    alert = AlertEvent(
        alert_rule_id=rule.id,
        device_id=device.id,
        location_id=device.location_id,
        severity=AlertSeverity.MEDIUM,
        message=f"{device.device_id} at {loc_name} is back online and operational.",
        status=AlertStatus.RESOLVED,
    )
    db.add(alert)
    await db.flush()

    logger.info("Device %s back online. Offline alerts resolved, online alert created.", device.device_id)
    return str(alert.id), str(device.location_id)


@celery_app.task(name="tasks.process_heartbeat", bind=True, max_retries=3)
def process_heartbeat(self, device_id: str, data: dict):
    try:
        asyncio.run(_process(device_id, data))
    except Exception as exc:
        logger.error("Heartbeat task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
