import json
import logging

import paho.mqtt.client as mqtt

from src.app.core.config import settings
from src.app.core.constants import MQTTTopics

logger = logging.getLogger("ai_parking.mqtt")

_mqtt_client: mqtt.Client = None


def _extract_device_id(topic: str) -> str:
    """Extract device_id from topic like parking/{device_id}/slots."""
    parts = topic.split("/")
    if len(parts) >= 2:
        return parts[1]
    return ""


def _topic_suffix(topic: str) -> str:
    """Extract the last segment of a topic (e.g. 'parking/lot-1/RPi-001/events' → 'events')."""
    return topic.rsplit("/", 1)[-1]


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logger.info("MQTT connected. Subscribing to topics...")
        client.subscribe([
            (MQTTTopics.ALL_SLOTS, settings.MQTT_QOS),
            (MQTTTopics.ALL_EVENTS, settings.MQTT_QOS),
            (MQTTTopics.ALL_HEARTBEATS, settings.MQTT_QOS),
            (MQTTTopics.ALL_STATUS, settings.MQTT_QOS),
            (MQTTTopics.ALL_ALERTS, settings.MQTT_QOS),
            (MQTTTopics.ALL_ACKS, settings.MQTT_QOS),
            (MQTTTopics.ALL_CMD_RESULTS, settings.MQTT_QOS),
            (MQTTTopics.ALL_SYNC, settings.MQTT_QOS),
        ])
    else:
        logger.error("MQTT connect failed: %s", reason_code)


def on_disconnect(client, userdata, flags, reason_code, properties):
    logger.warning("MQTT disconnected: reason_code=%s (0=clean, 142=session_takeover)", reason_code)


_TOPIC_HANDLERS = {
    "slots": "_handle_slot_snapshot",
    "events": "_handle_slot_events",
    "heartbeat": "_handle_heartbeat",
    "status": "_handle_device_status",
    "alerts": "_handle_device_alert",
    "ack": "_handle_ack",
    "cmd/result": "_handle_cmd_result",
    "sync/camera": "_handle_sync_camera",
    "sync/slots": "_handle_sync_slots",
}


def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode())
        logger.debug("MQTT message on %s: %s", topic, payload)

        device_id = payload.get("device_id") or _extract_device_id(topic)

        if not device_id:
            logger.warning("No device_id in message on %s", topic)
            return

        # Multi-level suffix topics: parking/{id}/sync/camera, parking/{id}/cmd/result
        if "/sync/" in topic:
            sync_type = topic.rsplit("/", 1)[-1]
            handler_name = _TOPIC_HANDLERS.get(f"sync/{sync_type}")
        elif "/cmd/" in topic:
            handler_name = _TOPIC_HANDLERS.get("cmd/result")
        else:
            handler_name = _TOPIC_HANDLERS.get(_topic_suffix(topic))

        if handler_name:
            globals()[handler_name](device_id, payload)
        else:
            logger.warning("Unhandled topic: %s", topic)

    except json.JSONDecodeError:
        logger.error("Invalid JSON payload on topic %s", msg.topic)
    except Exception:
        logger.exception("Error processing MQTT message on %s", msg.topic)


def _handle_slot_snapshot(device_id: str, payload: dict):
    """Dispatch full slot-state snapshot to Celery worker (reconciliation)."""
    from src.app.tasks.slot_update import process_slot_update

    slots = payload.get("slots", [])
    if not slots:
        logger.warning("Empty slots snapshot from %s", device_id)
        return

    process_slot_update.delay(device_id, slots)
    logger.info("Dispatched slot snapshot from %s (%d slots)", device_id, len(slots))


def _handle_slot_events(device_id: str, payload: dict):
    """Dispatch slot change events to Celery worker (real-time diffs)."""
    from src.app.tasks.slot_event import process_slot_event

    changes = payload.get("changes", [])
    if not changes:
        logger.warning("Empty slot events from %s", device_id)
        return

    camera_id = payload.get("camera_id")
    process_slot_event.delay(device_id, camera_id, changes)
    logger.info("Dispatched slot events from %s (%d changes)", device_id, len(changes))


def _handle_heartbeat(device_id: str, payload: dict):
    """Dispatch heartbeat telemetry to Celery worker."""
    from src.app.tasks.heartbeat import process_heartbeat

    process_heartbeat.delay(device_id, payload)


def _handle_device_status(device_id: str, payload: dict):
    """Dispatch device online/offline status to Celery worker."""
    import time
    from src.app.tasks.device_status import process_device_status

    # Skip stale retained OFFLINE messages only — stale "online" retained messages
    # are still valid (device was online when it published, might still be)
    ts = payload.get("timestamp")
    status = payload.get("status", "unknown")
    if ts and status == "offline" and (time.time() - float(ts)) > settings.DEVICE_OFFLINE_THRESHOLD_SECONDS:
        logger.debug("Skipping stale retained offline status from %s (age=%.0fs)", device_id, time.time() - float(ts))
        return

    process_device_status.delay(device_id, status, float(ts) if ts else None)
    logger.info("Device %s status: %s", device_id, status)


def _handle_device_alert(device_id: str, payload: dict):
    """Dispatch device alert to Celery worker."""
    from src.app.tasks.notifications import process_alert

    logger.warning("Device alert from %s: %s", device_id, payload.get("message"))
    process_alert.delay(json.dumps(payload))


def _handle_ack(device_id: str, payload: dict):
    """Dispatch command ACK to Celery worker."""
    from src.app.tasks.command_ack import process_command_ack

    process_command_ack.delay(device_id, payload)


def _handle_cmd_result(device_id: str, payload: dict):
    """Handle command results (e.g., snapshot image) — save to disk + update camera record."""
    import base64
    import os

    action = payload.get("action")
    command_id = payload.get("command_id", "")

    if action == "slot_snapshot":
        image_url = payload.get("image_url")
        slot_label = payload.get("slot_label")
        if image_url and command_id:
            from src.app.tasks.command_ack import store_command_result
            store_command_result.delay(command_id, {"image_url": image_url, "slot_label": slot_label})
        logger.info("Slot snapshot from %s: slot=%s url=%s cmd=%s", device_id, slot_label, image_url, command_id)

    elif action == "snapshot":
        image_b64 = payload.get("image_b64")
        if not image_b64:
            logger.warning("Snapshot result from %s has no image data", device_id)
            return

        os.makedirs("data/snapshots", exist_ok=True)
        camera_label = payload.get("camera_label", "unknown")
        path = f"data/snapshots/{device_id}_{camera_label}.jpg"
        width = payload.get("width")
        height = payload.get("height")

        with open(path, "wb") as f:
            f.write(base64.b64decode(image_b64))

        # Update camera record with frame dimensions + snapshot path
        from src.app.tasks.sync_camera import update_camera_snapshot
        update_camera_snapshot.delay(device_id, camera_label, path, width, height)

        logger.info("Snapshot saved: %s (%sx%s, cmd=%s)", path, width, height, command_id)
    else:
        logger.info("Command result from %s: action=%s", device_id, action)


def _handle_sync_camera(device_id: str, payload: dict):
    """Dispatch camera config sync to Celery worker."""
    from src.app.tasks.sync_camera import process_sync_camera

    action = payload.get("action", "upsert")
    camera = payload.get("camera", {})
    process_sync_camera.delay(device_id, action, camera)
    logger.info("Dispatched camera sync from %s: %s %s", device_id, action, camera.get("label"))


def _handle_sync_slots(device_id: str, payload: dict):
    """Dispatch slots config sync to Celery worker."""
    from src.app.tasks.sync_slots import process_sync_slots

    action = payload.get("action", "upsert")
    camera_label = payload.get("camera_label", "")
    slots = payload.get("slots", [])
    process_sync_slots.delay(device_id, action, camera_label, slots)
    logger.info("Dispatched slots sync from %s: %s %s (%d slots)", device_id, action, camera_label, len(slots))


def get_mqtt_client() -> mqtt.Client:
    global _mqtt_client
    if _mqtt_client is None:
        import uuid
        unique_id = f"{settings.MQTT_CLIENT_ID}-{uuid.uuid4().hex[:8]}"
        _mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=unique_id,
            protocol=mqtt.MQTTv5,
        )
        logger.info("MQTT client_id: %s", unique_id)
        _mqtt_client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        _mqtt_client.on_connect = on_connect
        _mqtt_client.on_disconnect = on_disconnect
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
    if not client.is_connected():
        logger.error("MQTT not connected — command to %s lost: %s", device_id, topic_template)
        return
    topic = topic_template.format(device_id=device_id)
    result = client.publish(topic, json.dumps(payload), qos=settings.MQTT_QOS)
    if result.rc != 0:
        logger.error("MQTT publish failed (rc=%d) to %s", result.rc, topic)
    else:
        logger.info("Published command to %s", topic)
