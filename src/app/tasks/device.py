"""Celery tasks: Device offline detection and OTA deployment."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.app.core.config import settings
from src.app.core.constants import (
    DeviceStatus, AlertSeverity, AlertStatus, AlertTriggerType,
)
from src.app.db.session import get_celery_session_factory
from src.app.models.device import Device
from src.app.models.alert_rule import AlertRule
from src.app.models.alert_event import AlertEvent

logger = logging.getLogger("ai_parking.tasks.device")


async def _check_heartbeats():
    async with get_celery_session_factory()() as db:
        try:
            threshold = datetime.now(timezone.utc) - timedelta(
                seconds=settings.DEVICE_OFFLINE_THRESHOLD_SECONDS
            )

            # Find devices that are ONLINE but haven't sent heartbeat
            result = await db.execute(
                select(Device).where(
                    Device.status == DeviceStatus.ONLINE,
                    Device.last_seen < threshold,
                )
            )
            stale_devices = result.scalars().all()

            if not stale_devices:
                logger.debug("All devices healthy")
                return

            # Get or use default alert rule for device offline
            result = await db.execute(
                select(AlertRule).where(
                    AlertRule.trigger_type == AlertTriggerType.DEVICE_OFFLINE,
                    AlertRule.is_active == True,
                )
            )
            rule = result.scalars().first()

            for device in stale_devices:
                # Mark device as OFFLINE
                await db.execute(
                    update(Device)
                    .where(Device.id == device.id)
                    .values(status=DeviceStatus.OFFLINE)
                )

                # Check if there's already an active alert for this device
                result = await db.execute(
                    select(AlertEvent).where(
                        AlertEvent.device_id == device.id,
                        AlertEvent.status == AlertStatus.ACTIVE,
                    )
                )
                existing_alert = result.scalars().first()
                if existing_alert:
                    continue

                # Create alert event
                if rule:
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

                    logger.warning(
                        "Device %s marked OFFLINE. Alert created.", device.device_id
                    )

                    # Dispatch notification task
                    from src.app.tasks.notifications import dispatch_alert_notifications
                    await db.flush()
                    dispatch_alert_notifications.delay(
                        str(alert.id), str(device.location_id)
                    )

            await db.commit()
            logger.info(
                "Heartbeat check complete. %d device(s) marked offline.",
                len(stale_devices),
            )

        except Exception:
            await db.rollback()
            logger.exception("Failed to check device heartbeats")
            raise


@celery_app.task(name="tasks.check_device_heartbeats")
def check_device_heartbeats():
    asyncio.run(_check_heartbeats())


@celery_app.task(name="tasks.process_ota_deployment")
def process_ota_deployment(deployment_id: str):
    logger.info("Processing OTA deployment %s", deployment_id)
