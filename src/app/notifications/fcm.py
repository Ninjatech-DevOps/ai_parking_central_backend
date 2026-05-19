"""Firebase Cloud Messaging (FCM) push notification sender.
Works for both web (React) and mobile apps."""

import logging
from typing import List

from src.app.core.config import settings

logger = logging.getLogger("ai_parking.notifications.fcm")

_firebase_initialized = False


def _init_firebase():
    global _firebase_initialized
    if _firebase_initialized:
        return True

    if not settings.FIREBASE_CREDENTIALS_PATH:
        logger.warning("Firebase credentials not configured. Skipping push notifications.")
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred, {
            "projectId": settings.FIREBASE_PROJECT_ID,
        })
        _firebase_initialized = True
        logger.info("Firebase initialized successfully")
        return True

    except Exception:
        logger.exception("Failed to initialize Firebase")
        return False


def send_push(tokens: List[str], title: str, body: str, data: dict = None) -> tuple[bool, List[str]]:
    """Send push notification to FCM tokens.
    Returns (success, stale_tokens) — stale_tokens should be removed from the user.
    """
    if not tokens:
        logger.debug("No FCM tokens provided. Skipping push.")
        return False, []

    if not _init_firebase():
        return False, []

    try:
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data={k: str(v) for k, v in (data or {}).items()},
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    icon="/favicon.ico",
                    badge="/favicon.ico",
                ),
            ),
        )

        response = messaging.send_each_for_multicast(message)
        logger.info(
            "FCM push sent: %d success, %d failure",
            response.success_count,
            response.failure_count,
        )

        stale_tokens = []
        for i, send_response in enumerate(response.responses):
            if not send_response.success:
                error_str = str(send_response.exception)
                logger.warning(
                    "FCM token failed: %s — %s",
                    tokens[i][:30],
                    error_str,
                )
                # Collect stale/invalid tokens for cleanup
                if "NotRegistered" in error_str or "InvalidArgument" in error_str:
                    stale_tokens.append(tokens[i])

        return response.success_count > 0, stale_tokens

    except Exception:
        logger.exception("Failed to send FCM push")
        return False, []
