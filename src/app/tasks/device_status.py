"""Celery task: Process device online/offline status from /status topic + LWT."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.app.core.constants import (
    DeviceStatus, AlertSeverity, AlertStatus, AlertTriggerType,
)
from src.app.db.session import get_celery_session_factory
from src.app.models.device import Device
from src.app.models.alert_rule import AlertRule
from src.app.models.alert_event import AlertEvent

logger = logging.getLogger("ai_parking.tasks.device_status")

_STATUS_MAP = {
    "online": DeviceStatus.ONLINE,
    "offline": DeviceStatus.OFFLINE,
}


async def _process(device_id_str: str, status: str):
    async with get_celery_session_factory()() as db:
        try:
            # FOR UPDATE to prevent race conditions with concurrent heartbeat tasks
            result = await db.execute(
                select(Device)
                .where(Device.device_id == device_id_str)
                .with_for_update()
            )
            device = result.scalars().first()
            if not device:
                logger.warning("Status from unknown device: %s", device_id_str)
                return

            new_status = _STATUS_MAP.get(status.lower())
            if not new_status:
                logger.warning("Unknown status value '%s' from device %s", status, device_id_str)
                return

            previous_status = device.status
            now = datetime.now(timezone.utc)

            await db.execute(
                update(Device).where(Device.id == device.id).values(
                    status=new_status, last_seen=now
                )
            )

            # Device went OFFLINE (LWT message) — create alert + notify
            if new_status == DeviceStatus.OFFLINE and previous_status != DeviceStatus.OFFLINE:
                await _handle_device_went_offline(db, device, now)

            # Device came back online via explicit status message
            if new_status == DeviceStatus.ONLINE and previous_status == DeviceStatus.OFFLINE:
                await _handle_device_back_online(db, device, now)

            await db.commit()
            logger.info("Device %s → %s", device_id_str, new_status.value)

        except Exception:
            await db.rollback()
            logger.exception("Failed to process status for %s", device_id_str)
            raise


async def _handle_device_went_offline(db, device, now):
    """Create DEVICE_OFFLINE alert and dispatch notifications."""
    # Check if there's already an active offline alert for this device
    result = await db.execute(
        select(AlertEvent).where(
            AlertEvent.device_id == device.id,
            AlertEvent.status == AlertStatus.ACTIVE,
        )
    )
    if result.scalars().first():
        return  # Already has an active alert

    # Get DEVICE_OFFLINE alert rule
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.trigger_type == AlertTriggerType.DEVICE_OFFLINE,
            AlertRule.is_active == True,
        )
    )
    rule = result.scalars().first()
    if not rule:
        logger.warning("No DEVICE_OFFLINE alert rule found.")
        return

    loc_name = device.location.name if device.location else "Unknown"
    alert = AlertEvent(
        alert_rule_id=rule.id,
        device_id=device.id,
        location_id=device.location_id,
        severity=AlertSeverity.CRITICAL,
        message=(
            f"{device.device_id} at {loc_name} is offline and not responding. "
            f"Immediate attention required."
        ),
        status=AlertStatus.ACTIVE,
    )
    db.add(alert)
    await db.flush()

    from src.app.tasks.notifications import dispatch_alert_notifications
    dispatch_alert_notifications.delay(str(alert.id), str(device.location_id))
    logger.warning("Device %s went OFFLINE. Alert created.", device.device_id)


async def _handle_device_back_online(db, device, now):
    """Resolve active DEVICE_OFFLINE alerts and create a DEVICE_ONLINE alert."""
    # Auto-resolve any active alerts for this device
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
        return

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

    from src.app.tasks.notifications import dispatch_alert_notifications
    dispatch_alert_notifications.delay(str(alert.id), str(device.location_id))


@celery_app.task(name="tasks.process_device_status", bind=True, max_retries=3)
def process_device_status(self, device_id: str, status: str):
    try:
        asyncio.run(_process(device_id, status))
    except Exception as exc:
        logger.error("Device status task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
