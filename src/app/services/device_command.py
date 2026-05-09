import json
import uuid
from typing import Any, Dict, List, Optional

from src.app.core.constants import CommandType, CommandStatus, MQTTTopics
from src.app.exceptions.base import BadRequestException, NotFoundException
from src.app.mqtt.client import publish_command
from src.app.repositories.device import DeviceRepository
from src.app.repositories.device_command import DeviceCommandRepository


COMMAND_TOPIC_MAP = {
    CommandType.RESTART: MQTTTopics.CMD_RESTART,
    CommandType.UPDATE: MQTTTopics.CMD_UPDATE,
    CommandType.CONFIG: MQTTTopics.CMD_CONFIG,
    CommandType.SHELL: MQTTTopics.CMD_SHELL,
    CommandType.SNAPSHOT: MQTTTopics.CMD_SNAPSHOT,
}


class DeviceCommandService:
    def __init__(
        self,
        command_repo: DeviceCommandRepository,
        device_repo: DeviceRepository,
    ):
        self.command_repo = command_repo
        self.device_repo = device_repo

    async def send_command(
        self,
        device_uuid: uuid.UUID,
        command_type: CommandType,
        payload: Optional[str],
        sent_by: uuid.UUID,
    ) -> Any:
        device = await self.device_repo.get_by_id(device_uuid)
        if not device:
            raise NotFoundException(detail="Device not found")

        # Create command record
        command = await self.command_repo.create({
            "device_id": device.id,
            "command_type": command_type,
            "payload": payload,
            "status": CommandStatus.SENT,
            "sent_by": sent_by,
        })

        # Build MQTT payload
        mqtt_payload = {
            "command_id": str(command.id),
            "action": command_type.value,
        }
        if payload:
            try:
                mqtt_payload["payload"] = json.loads(payload)
            except json.JSONDecodeError:
                mqtt_payload["payload"] = payload

        # Publish to MQTT
        topic_template = COMMAND_TOPIC_MAP.get(command_type)
        if topic_template:
            publish_command(device.device_id, topic_template, mqtt_payload)

        return command

    async def get_command(self, command_id: uuid.UUID) -> Any:
        command = await self.command_repo.get_by_id(command_id)
        if not command:
            raise NotFoundException(detail="Command not found")
        return command

    async def get_device_commands(
        self, device_uuid: uuid.UUID, limit: int = 20
    ) -> List[Any]:
        device = await self.device_repo.get_by_id(device_uuid)
        if not device:
            raise NotFoundException(detail="Device not found")
        return await self.command_repo.get_by_device_id(device.id, limit=limit)

    async def get_all(
        self, skip: int = 0, limit: int = 20, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        return await self.command_repo.get_all(skip=skip, limit=limit, filters=filters)

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        return await self.command_repo.count(filters=filters)
