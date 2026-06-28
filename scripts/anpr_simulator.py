#!/usr/bin/env python3
"""
ANPR Simulation Script — Publishes fake ANPR records via MQTT.

Simulates vehicles entering and exiting a parking location.
The Central BE receives these via MQTT → Celery → DB, and the FE can display them.

Usage:
    python scripts/anpr_simulator.py

Configure via environment variables or edit the constants below.
"""

import json
import random
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# ─── Configuration ────────────────────────────────────────────────────────────
MQTT_BROKER = "15.235.50.88"
MQTT_PORT = 41883
MQTT_USERNAME = "admin"
MQTT_PASSWORD = "Broker@123"

DEVICE_ID = "RPI-001"  # Must match a device_id in the DB
CAMERA_LABEL = "ccl"  # Must match a camera position_label on this device

# Interval between events (seconds)
MIN_INTERVAL = 5
MAX_INTERVAL = 15

# Probability of OUT event (vs IN) — starts low, increases as vehicles accumulate
BASE_OUT_PROBABILITY = 0.3

# ─── Sample Data ──────────────────────────────────────────────────────────────
INDIAN_PLATES = [
    "GJ01AB1234", "GJ01CD5678", "GJ01EF9012", "GJ01GH3456",
    "GJ05JK7890", "GJ05LM2345", "GJ05NP6789", "GJ05QR0123",
    "GJ27ST4567", "GJ27UV8901", "GJ27WX2345", "GJ27YZ6789",
    "MH01AA1111", "MH01BB2222", "MH04CC3333", "MH12DD4444",
    "RJ14EE5555", "RJ14FF6666", "DL01GG7777", "DL02HH8888",
    "KA01II9999", "KA05JJ0000", "TN01KK1111", "AP09LL2222",
    "GJ03MM3333", "GJ03NN4444", "GJ06PP5555", "GJ06RR6666",
    "GJ01TT7777", "GJ01UU8888",
]

VEHICLE_TYPES = ["CAR", "CAR", "CAR", "TWO_WHEELER"]  # 75% cars, 25% two-wheelers

# Track which vehicles are "inside" for realistic IN/OUT matching
vehicles_inside: dict[str, dict] = {}  # plate -> {vehicle_type, entered_at}


def generate_plate_ocr(real_plate: str) -> tuple[str, str, float, float]:
    """Simulate dual OCR results with occasional misreads."""
    gemini_conf = round(random.uniform(0.85, 0.99), 2)
    paddle_conf = round(random.uniform(0.80, 0.97), 2)

    # 10% chance of slight paddle misread
    paddle_plate = real_plate
    if random.random() < 0.10:
        chars = list(real_plate)
        idx = random.randint(4, len(chars) - 1)
        chars[idx] = str(random.randint(0, 9))
        paddle_plate = "".join(chars)
        paddle_conf = round(random.uniform(0.55, 0.75), 2)

    return real_plate, paddle_plate, gemini_conf, paddle_conf


def create_anpr_event() -> dict:
    """Generate a realistic ANPR event."""
    # Decide IN or OUT
    if vehicles_inside and random.random() < min(0.7, BASE_OUT_PROBABILITY + len(vehicles_inside) * 0.05):
        # OUT event — pick a random vehicle that's inside
        plate = random.choice(list(vehicles_inside.keys()))
        info = vehicles_inside.pop(plate)
        direction = "OUT"
        vehicle_type = info["vehicle_type"]
    else:
        # IN event — pick a random plate
        plate = random.choice(INDIAN_PLATES)
        vehicle_type = random.choice(VEHICLE_TYPES)
        direction = "IN"
        vehicles_inside[plate] = {"vehicle_type": vehicle_type, "entered_at": datetime.now(timezone.utc)}

    gemini_plate, paddle_plate, gemini_conf, paddle_conf = generate_plate_ocr(plate)

    return {
        "device_id": DEVICE_ID,
        "camera_label": CAMERA_LABEL,
        "number_plate": gemini_plate,  # Use Gemini result as primary
        "vehicle_type": vehicle_type,
        "direction": direction,
        "image_url": f"https://api-minio.projectanddemoserver.com/ai-parking/anpr/sim_{plate}_{int(time.time())}.jpg",
        "gemini_result": gemini_plate,
        "paddle_result": paddle_plate,
        "confidence_gemini": gemini_conf,
        "confidence_paddle": paddle_conf,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"✓ Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"✗ Connection failed: {reason_code}")


def main():
    client_id = f"anpr-simulator-{uuid.uuid4().hex[:8]}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv5)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect

    print(f"Connecting to {MQTT_BROKER}:{MQTT_PORT} as {client_id}...")
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
    time.sleep(2)

    topic = f"anpr/{DEVICE_ID}/record"
    print(f"\nPublishing ANPR events to: {topic}")
    print(f"Interval: {MIN_INTERVAL}-{MAX_INTERVAL}s")
    print("-" * 60)

    event_count = 0
    try:
        while True:
            event = create_anpr_event()
            payload = json.dumps(event)
            result = client.publish(topic, payload, qos=1)

            event_count += 1
            direction_icon = "→" if event["direction"] == "IN" else "←"
            print(
                f"[{event_count:4d}] {direction_icon} {event['direction']:3s} | "
                f"{event['number_plate']:12s} | {event['vehicle_type']:12s} | "
                f"Gemini={event['confidence_gemini']:.2f} Paddle={event['confidence_paddle']:.2f} | "
                f"Inside: {len(vehicles_inside)}"
            )

            interval = random.uniform(MIN_INTERVAL, MAX_INTERVAL)
            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n\nStopped. Sent {event_count} events. {len(vehicles_inside)} vehicles still inside.")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
