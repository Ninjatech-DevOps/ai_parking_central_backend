from celery import Celery

from src.app.core.config import settings

celery_app = Celery(
    "ai_parking",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.autodiscover_tasks(["src.app.tasks"])

celery_app.conf.beat_schedule = {
    "check-device-heartbeats": {
        "task": "tasks.check_device_heartbeats",
        "schedule": settings.DEVICE_HEARTBEAT_INTERVAL_SECONDS,
    },
}
