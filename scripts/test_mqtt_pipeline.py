"""
Test script: Simulate edge device sending MQTT messages.
Publishes slot updates and heartbeats to the VPS broker.
"""

import json
import time

import paho.mqtt.client as mqtt

BROKER = "15.235.50.88"
PORT = 41883
USERNAME = "admin"
PASSWORD = "Broker@123"
DEVICE_ID = "RPi-TEST-001"
LOT_ID = "test-lot"

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id="test-edge-device",
    protocol=mqtt.MQTTv5,
)
client.username_pw_set(USERNAME, PASSWORD)
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()

print("Connected to MQTT broker")
print()

# 1. Send heartbeat
print("--- Sending heartbeat ---")
heartbeat = {
    "device_id": DEVICE_ID,
    "cpu_percent": 23.5,
    "temperature": 45.2,
    "memory_percent": 62.1,
    "disk_percent": 34.0,
    "uptime_seconds": 86400,
    "cameras": [
        {"id": "CAM-001-L", "status": "ACTIVE"},
        {"id": "CAM-001-R", "status": "ACTIVE"},
    ],
}
topic = f"parking/{LOT_ID}/{DEVICE_ID}/heartbeat"
client.publish(topic, json.dumps(heartbeat), qos=1)
print(f"Published to {topic}")
time.sleep(2)

# 2. Send slot updates
print()
print("--- Sending slot updates ---")
slot_update = {
    "device_id": DEVICE_ID,
    "slots": [
        {"slot_label": "A-01", "state": "VEHICLE"},
        {"slot_label": "A-02", "state": "VEHICLE"},
        {"slot_label": "A-03", "state": "EMPTY"},
        {"slot_label": "A-04", "state": "OBSTRUCTED"},
        {"slot_label": "A-05", "state": "VEHICLE"},
    ],
}
topic = f"parking/{LOT_ID}/{DEVICE_ID}/slots"
client.publish(topic, json.dumps(slot_update), qos=1)
print(f"Published to {topic}")
time.sleep(2)

# 3. Send second update (state change for A-01)
print()
print("--- Sending state change for A-01 (VEHICLE -> EMPTY) ---")
slot_update_2 = {
    "device_id": DEVICE_ID,
    "slots": [
        {"slot_label": "A-01", "state": "EMPTY"},
    ],
}
client.publish(topic, json.dumps(slot_update_2), qos=1)
print(f"Published to {topic}")
time.sleep(2)

print()
print("=== All messages sent. Check API for results. ===")

client.loop_stop()
client.disconnect()
