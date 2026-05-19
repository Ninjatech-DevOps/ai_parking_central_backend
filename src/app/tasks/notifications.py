"""Celery tasks: Alert notification dispatcher + push/email senders."""

import asyncio
import logging
import uuid

from sqlalchemy import select

from src.celery_app import celery_app
from src.app.core.constants import AlertSeverity, NotificationChannel
from src.app.db.session import get_celery_session_factory
from src.app.models.alert_event import AlertEvent
from src.app.models.user import User
from src.app.models.notification_preference import NotificationPreference
from src.app.models.notification_log import NotificationLog
from src.app.services.scope_resolver import ScopeResolver

logger = logging.getLogger("ai_parking.tasks.notifications")

# CRITICAL alerts always send all channels regardless of user preferences
CRITICAL_FORCE_CHANNELS = [
    NotificationChannel.PUSH, NotificationChannel.EMAIL, NotificationChannel.IN_APP,
]

# Default channels when user has no preferences configured
DEFAULT_CHANNELS = [
    NotificationChannel.EMAIL, NotificationChannel.IN_APP,
]


def _severity_label(severity) -> str:
    """Get clean string from severity enum or string."""
    return severity.value if hasattr(severity, "value") else str(severity)


def _build_push_title(severity) -> str:
    label = _severity_label(severity)
    if label == "CRITICAL":
        return "CRITICAL: Device Offline"
    elif label == "MEDIUM":
        return "Device Status Update"
    return f"AI Parking Alert ({label})"


def _build_email_subject(severity, message: str) -> str:
    label = _severity_label(severity)
    # Extract a short summary from the message
    if "offline" in message.lower():
        return f"[{label}] Device Offline Alert"
    elif "back online" in message.lower():
        return f"[{label}] Device Back Online"
    return f"[{label}] AI Parking Alert"


async def _dispatch_alert_notifications(alert_event_id: str, location_id: str):
    async with get_celery_session_factory()() as db:
        try:
            # Get alert event
            result = await db.execute(
                select(AlertEvent).where(
                    AlertEvent.id == uuid.UUID(alert_event_id)
                )
            )
            alert = result.scalars().first()
            if not alert:
                logger.warning("Alert event %s not found", alert_event_id)
                return

            # Resolve users who should be notified (cascading scopes)
            resolver = ScopeResolver(db)
            user_ids = await resolver.resolve_users_for_location(
                uuid.UUID(location_id)
            )

            if not user_ids:
                logger.info("No users to notify for alert %s", alert_event_id)
                return

            # Get users
            result = await db.execute(
                select(User).where(User.id.in_(user_ids), User.is_active == True)
            )
            users = result.scalars().all()

            push_title = _build_push_title(alert.severity)
            email_subject = _build_email_subject(alert.severity, alert.message)

            notified_count = 0
            for user in users:
                channels = await _get_channels_for_user(
                    db, user.id, alert.severity
                )

                for channel in channels:
                    # Log the notification
                    log = NotificationLog(
                        user_id=user.id,
                        alert_event_id=alert.id,
                        channel=channel,
                        status="SENT",
                    )
                    db.add(log)

                    # Dispatch actual send
                    if channel == NotificationChannel.PUSH and user.fcm_tokens:
                        send_push_notification.delay(
                            str(user.id),
                            push_title,
                            alert.message,
                            user.fcm_tokens,
                            {"severity": _severity_label(alert.severity)},
                        )
                    elif channel == NotificationChannel.EMAIL:
                        send_email_notification.delay(
                            user.email,
                            email_subject,
                            alert.message,
                        )

                    notified_count += 1

            await db.commit()
            logger.info(
                "Alert %s: notified %d user(s) via %d notification(s)",
                alert_event_id, len(users), notified_count,
            )

        except Exception:
            await db.rollback()
            logger.exception("Failed to dispatch notifications for alert %s", alert_event_id)
            raise


async def _get_channels_for_user(
    db, user_id: uuid.UUID, severity: str
) -> list[NotificationChannel]:
    """Get notification channels for a user based on severity + preferences."""
    # CRITICAL always forces all channels regardless of preferences
    if severity == AlertSeverity.CRITICAL:
        return CRITICAL_FORCE_CHANNELS[:]

    # Check user preferences
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.alert_severity == severity,
            NotificationPreference.is_enabled == True,
        )
    )
    prefs = result.scalars().all()

    if prefs:
        return [NotificationChannel(p.channel) for p in prefs]

    # Default: EMAIL + IN_APP when no preferences configured
    return DEFAULT_CHANNELS[:]


@celery_app.task(name="tasks.dispatch_alert_notifications", bind=True, max_retries=3)
def dispatch_alert_notifications(self, alert_event_id: str, location_id: str):
    try:
        asyncio.run(_dispatch_alert_notifications(alert_event_id, location_id))
    except Exception as exc:
        logger.error("Notification dispatch failed, retrying: %s", exc)
        self.retry(countdown=5, exc=exc)


@celery_app.task(name="tasks.send_push_notification", bind=True, max_retries=3)
def send_push_notification(self, user_id: str, title: str, body: str, fcm_tokens: list, data: dict = None):
    from src.app.notifications.fcm import send_push
    try:
        success, stale_tokens = send_push(tokens=fcm_tokens, title=title, body=body, data=data)
        if success:
            logger.info("PUSH sent to user %s: %s", user_id, title)
        else:
            logger.warning("PUSH skipped/failed for user %s", user_id)

        # Auto-cleanup stale tokens
        if stale_tokens:
            _cleanup_stale_tokens.delay(user_id, stale_tokens)
    except Exception as exc:
        logger.error("PUSH task failed, retrying: %s", exc)
        self.retry(countdown=10, exc=exc)


@celery_app.task(name="tasks.cleanup_stale_fcm_tokens")
def _cleanup_stale_tokens(user_id: str, stale_tokens: list):
    """Remove stale/unregistered FCM tokens from a user."""
    async def _do():
        from sqlalchemy import update as sa_update
        async with get_celery_session_factory()() as db:
            result = await db.execute(
                select(User).where(User.id == uuid.UUID(user_id))
            )
            user = result.scalars().first()
            if not user:
                return
            current = list(user.fcm_tokens or [])
            cleaned = [t for t in current if t not in stale_tokens]
            if len(cleaned) != len(current):
                await db.execute(
                    sa_update(User)
                    .where(User.id == user.id)
                    .values(fcm_tokens=cleaned)
                )
                await db.commit()
                logger.info(
                    "Cleaned %d stale FCM token(s) for user %s",
                    len(current) - len(cleaned), user_id,
                )
    asyncio.run(_do())


@celery_app.task(name="tasks.send_email_notification", bind=True, max_retries=3)
def send_email_notification(self, to_email: str, subject: str, body: str):
    from src.app.notifications.email import send_email
    try:
        success = send_email(to_email=to_email, subject=subject, body=body)
        if success:
            logger.info("EMAIL sent to %s: %s", to_email, subject)
        else:
            logger.warning("EMAIL skipped/failed for %s", to_email)
    except Exception as exc:
        logger.error("EMAIL task failed, retrying: %s", exc)
        self.retry(countdown=10, exc=exc)


@celery_app.task(name="tasks.process_alert")
def process_alert(alert_event_id: str):
    logger.info("Processing alert event %s", alert_event_id)
