"""Service: Push camera/slot config from Central to edge devices via MQTT commands."""

import logging
from typing import Dict, List, Optional

from src.app.core.constants import MQTTTopics
from src.app.mqtt.client import publish_command

logger = logging.getLogger("ai_parking.services.device_config_push")


def push_camera_config(device_id: str, action: str, camera_data: Dict) -> None:
    """Push camera create/update/delete to edge device."""
    publish_command(device_id, MQTTTopics.CMD_CONFIG_CAMERA, {
        "action": action,
        "payload": camera_data,
    })
    logger.info("Pushed camera config to %s: %s %s", device_id, action, camera_data.get("label"))


def push_slots_config(device_id: str, camera_label: str, slots: List[Dict]) -> None:
    """Push slot polygon config to edge device."""
    publish_command(device_id, MQTTTopics.CMD_CONFIG_SLOTS, {
        "action": "upsert",
        "payload": {
            "camera_label": camera_label,
            "slots": slots,
        },
    })
    logger.info("Pushed %d slots config to %s (camera=%s)", len(slots), device_id, camera_label)


def push_calibrate(device_id: str, camera_label: str, slot_label: str) -> None:
    """Trigger slot calibration on edge device."""
    publish_command(device_id, MQTTTopics.CMD_CALIBRATE, {
        "action": "calibrate",
        "payload": {
            "camera_label": camera_label,
            "slot_label": slot_label,
        },
    })
    logger.info("Pushed calibrate to %s: %s/%s", device_id, camera_label, slot_label)
