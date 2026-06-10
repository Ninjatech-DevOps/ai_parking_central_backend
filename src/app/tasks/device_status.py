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


async def _process(device_id_str: str, status: str, msg_timestamp: float = None):
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

            # Reject out-of-order messages: if the device was seen MORE recently
            # than this message's timestamp, skip it (Celery doesn't guarantee order)
            if msg_timestamp and device.last_seen:
                msg_time = datetime.fromtimestamp(msg_timestamp, tz=timezone.utc)
                if msg_time < device.last_seen:
                    logger.info(
                        "Skipping out-of-order status '%s' for %s (msg_time=%s < last_seen=%s)",
                        status, device_id_str, msg_time.isoformat(), device.last_seen.isoformat(),
                    )
                    return

            previous_status = device.status
            now = datetime.now(timezone.utc)

            await db.execute(
                update(Device).where(Device.id == device.id).values(
                    status=new_status, last_seen=now
                )
            )

            # Collect notification to dispatch AFTER commit
            pending_notification = None

            # Device went OFFLINE (LWT message) — create alert + notify
            if new_status == DeviceStatus.OFFLINE and previous_status != DeviceStatus.OFFLINE:
                pending_notification = await _handle_device_went_offline(db, device, now)

            # Device came back online via explicit status message
            if new_status == DeviceStatus.ONLINE and previous_status == DeviceStatus.OFFLINE:
                pending_notification = await _handle_device_back_online(db, device, now)

            await db.commit()
            logger.info("Device %s → %s", device_id_str, new_status.value)

            # Dispatch notifications AFTER commit so alert row is visible to notification worker
            if pending_notification:
                from src.app.tasks.notifications import dispatch_alert_notifications
                dispatch_alert_notifications.delay(*pending_notification)

        except Exception:
            await db.rollback()
            logger.exception("Failed to process status for %s", device_id_str)
            raise


async def _handle_device_went_offline(db, device, now):
    """Create DEVICE_OFFLINE alert. Returns (alert_id, location_id) for post-commit dispatch, or None."""
    # Check if there's already an active offline alert for this device
    result = await db.execute(
        select(AlertEvent).where(
            AlertEvent.device_id == device.id,
            AlertEvent.status == AlertStatus.ACTIVE,
        )
    )
    if result.scalars().first():
        return None  # Already has an active alert

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
        return None

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

    logger.warning("Device %s went OFFLINE. Alert created.", device.device_id)
    return str(alert.id), str(device.location_id)


async def _handle_device_back_online(db, device, now):
    """Resolve active DEVICE_OFFLINE alerts and create a DEVICE_ONLINE alert.
    Returns (alert_id, location_id) for post-commit dispatch, or None.
    """
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
        return None

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

    return str(alert.id), str(device.location_id)


@celery_app.task(name="tasks.process_device_status", bind=True, max_retries=3)
def process_device_status(self, device_id: str, status: str, msg_timestamp: float = None):
    try:
        asyncio.run(_process(device_id, status, msg_timestamp))
    except Exception as exc:
        logger.error("Device status task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)
