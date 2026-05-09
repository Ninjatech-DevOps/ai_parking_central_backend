import json
import logging

import paho.mqtt.client as mqtt

from src.app.core.config import settings
from src.app.core.constants import MQTTTopics

logger = logging.getLogger("ai_parking.mqtt")

_mqtt_client: mqtt.Client = None


def _extract_device_id(topic: str) -> str:
    """Extract device_id from topic like parking/{lot_id}/{device_id}/slots."""
    parts = topic.split("/")
    if len(parts) >= 3:
        return parts[2]
    return ""


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logger.info("MQTT connected. Subscribing to topics...")
        client.subscribe([
            (MQTTTopics.ALL_SLOTS, settings.MQTT_QOS),
            (MQTTTopics.ALL_HEARTBEATS, settings.MQTT_QOS),
            (MQTTTopics.ALL_ALERTS, settings.MQTT_QOS),
            (MQTTTopics.ALL_ACKS, settings.MQTT_QOS),
        ])
    else:
        logger.error("MQTT connect failed: %s", reason_code)


def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode())
        logger.debug("MQTT message on %s: %s", topic, payload)

        device_id = payload.get("device_id") or _extract_device_id(topic)

        if not device_id:
            logger.warning("No device_id in message on %s", topic)
            return

        if "/slots" in topic:
            _handle_slot_update(device_id, payload)
        elif "/heartbeat" in topic:
            _handle_heartbeat(device_id, payload)
        elif "/alerts" in topic:
            _handle_device_alert(device_id, payload)
        elif "/ack" in topic:
            _handle_ack(device_id, payload)

    except json.JSONDecodeError:
        logger.error("Invalid JSON payload on topic %s", msg.topic)
    except Exception:
        logger.exception("Error processing MQTT message on %s", msg.topic)


def _handle_slot_update(device_id: str, payload: dict):
    """Dispatch slot update to Celery worker."""
    from src.app.tasks.slot_update import process_slot_update

    slots = payload.get("slots", [])
    if not slots:
        logger.warning("Empty slots in message from %s", device_id)
        return

    process_slot_update.delay(device_id, slots)
    logger.info("Dispatched slot update from %s (%d slots)", device_id, len(slots))


def _handle_heartbeat(device_id: str, payload: dict):
    """Dispatch heartbeat to Celery worker."""
    from src.app.tasks.heartbeat import process_heartbeat

    process_heartbeat.delay(device_id, payload)


def _handle_device_alert(device_id: str, payload: dict):
    """Dispatch device alert to Celery worker."""
    from src.app.tasks.notifications import process_alert

    logger.warning("Device alert from %s: %s", device_id, payload.get("message"))
    process_alert.delay(json.dumps(payload))


def _handle_ack(device_id: str, payload: dict):
    """Dispatch command ACK to Celery worker."""
    from src.app.tasks.command_ack import process_command_ack

    process_command_ack.delay(device_id, payload)


def get_mqtt_client() -> mqtt.Client:
    global _mqtt_client
    if _mqtt_client is None:
        _mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv5,
        )
        _mqtt_client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        _mqtt_client.on_connect = on_connect
        _mqtt_client.on_message = on_message
    return _mqtt_client


def start_mqtt():
    client = get_mqtt_client()
    try:
        client.connect(
            settings.MQTT_BROKER_HOST,
            settings.MQTT_BROKER_PORT,
            keepalive=settings.MQTT_KEEPALIVE,
        )
        client.loop_start()
        logger.info("MQTT client started")
    except Exception:
        logger.exception("Failed to connect to MQTT broker")


def stop_mqtt():
    global _mqtt_client
    if _mqtt_client:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
        logger.info("MQTT client stopped")
        _mqtt_client = None


def publish_command(device_id: str, topic_template: str, payload: dict):
    client = get_mqtt_client()
    topic = topic_template.format(device_id=device_id)
    client.publish(topic, json.dumps(payload), qos=settings.MQTT_QOS)
    logger.info("Published command to %s: %s", topic, payload)
