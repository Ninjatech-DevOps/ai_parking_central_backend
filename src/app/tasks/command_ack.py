"""Celery task: Process command acknowledgements from edge devices."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import update

from src.celery_app import celery_app
from src.app.core.constants import CommandStatus
from src.app.db.session import get_celery_session_factory
from src.app.models.device_command import DeviceCommand

logger = logging.getLogger("ai_parking.tasks.command_ack")


async def _process(device_id_str: str, data: dict):
    async with get_celery_session_factory()() as db:
        try:
            command_id = data.get("command_id")
            status = data.get("status", "").lower()
            error = data.get("error")

            if not command_id:
                logger.debug("ACK without command_id from %s", device_id_str)
                return

            status_map = {
                "acknowledged": CommandStatus.ACKNOWLEDGED,
                "completed": CommandStatus.COMPLETED,
                "failed": CommandStatus.FAILED,
            }
            new_status = status_map.get(status)
            if not new_status:
                logger.warning("Unknown ACK status: %s", status)
                return

            values = {"status": new_status}
            if new_status in (CommandStatus.COMPLETED, CommandStatus.FAILED):
                values["completed_at"] = datetime.now(timezone.utc)
            if error:
                values["error_message"] = error

            await db.execute(
                update(DeviceCommand)
                .where(DeviceCommand.id == command_id)
                .values(**values)
            )
            await db.commit()
            logger.info("Command %s ACK: %s", command_id, status)

        except Exception:
            await db.rollback()
            logger.exception("Failed to process ACK from %s", device_id_str)
            raise


@celery_app.task(name="tasks.process_command_ack", bind=True, max_retries=3)
def process_command_ack(self, device_id: str, data: dict):
    try:
        asyncio.run(_process(device_id, data))
    except Exception as exc:
        logger.error("Command ACK task failed, retrying: %s", exc)
        self.retry(countdown=2, exc=exc)


async def _store_result(command_id: str, result: dict):
    import json
    async with get_celery_session_factory()() as db:
        try:
            await db.execute(
                update(DeviceCommand)
                .where(DeviceCommand.id == command_id)
                .values(result=json.dumps(result))
            )
            await db.commit()
            logger.info("Command %s result stored", command_id)
        except Exception:
            await db.rollback()
            logger.exception("Failed to store result for command %s", command_id)
            raise


@celery_app.task(name="tasks.store_command_result", bind=True, max_retries=3)
def store_command_result(self, command_id: str, result: dict):
    try:
        asyncio.run(_store_result(command_id, result))
    except Exception as exc:
        self.retry(countdown=2, exc=exc)
