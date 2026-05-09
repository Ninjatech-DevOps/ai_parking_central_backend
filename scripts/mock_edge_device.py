"""
Mock Edge Device — simulates an RPi5 connected to the MQTT broker.
- Sends heartbeats every 10 seconds
- Listens for commands (restart, update, snapshot, etc.)
- Sends ACKs back to central server

Usage: python scripts/mock_edge_device.py [device_id]
Default device_id: RPi-TEST-001
"""

import json
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

BROKER = "15.235.50.88"
PORT = 41883
USERNAME = "admin"
PASSWORD = "Broker@123"

DEVICE_ID = sys.argv[1] if len(sys.argv) > 1 else "RPi-TEST-001"
LOT_ID = "test-lot"

# Topics this device listens to
CMD_TOPIC = f"cmd/{DEVICE_ID}/#"

# Topics this device publishes to
HEARTBEAT_TOPIC = f"parking/{LOT_ID}/{DEVICE_ID}/heartbeat"
SLOT_TOPIC = f"parking/{LOT_ID}/{DEVICE_ID}/slots"
ACK_TOPIC = f"parking/{LOT_ID}/{DEVICE_ID}/ack"


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[{DEVICE_ID}] Connected to broker")
        client.subscribe(CMD_TOPIC, qos=1)
        print(f"[{DEVICE_ID}] Listening for commands on: {CMD_TOPIC}")
    else:
        print(f"[{DEVICE_ID}] Connect failed: {reason_code}")


def on_message(client, userdata, msg):
    """Handle commands from central server."""
    try:
        command = json.loads(msg.payload.decode())
        action = command.get("action", "unknown")
        command_id = command.get("command_id")
        payload = command.get("payload")

        print(f"\n[{DEVICE_ID}] Received command: {action}")
        print(f"  Topic: {msg.topic}")
        print(f"  Command ID: {command_id}")
        if payload:
            print(f"  Payload: {payload}")

        # Send ACK — acknowledged
        ack = {
            "device_id": DEVICE_ID,
            "command_id": command_id,
            "action": action,
            "status": "acknowledged",
        }
        client.publish(ACK_TOPIC, json.dumps(ack), qos=1)
        print(f"[{DEVICE_ID}] Sent ACK: acknowledged")

        # Simulate processing
        time.sleep(1)

        # Handle specific commands
        if action == "RESTART":
            print(f"[{DEVICE_ID}] Simulating restart...")
            time.sleep(2)
            status = "completed"

        elif action == "UPDATE":
            image = payload.get("image", "unknown") if isinstance(payload, dict) else payload
            print(f"[{DEVICE_ID}] Simulating update to {image}...")
            time.sleep(3)
            status = "completed"

        elif action == "SNAPSHOT":
            print(f"[{DEVICE_ID}] Simulating camera snapshot...")
            time.sleep(1)
            status = "completed"

        elif action == "CONFIG":
            print(f"[{DEVICE_ID}] Applying config: {payload}")
            status = "completed"

        elif action == "SHELL":
            print(f"[{DEVICE_ID}] Running shell command: {payload}")
            status = "completed"

        else:
            print(f"[{DEVICE_ID}] Unknown command: {action}")
            status = "failed"

        # Send ACK — completed/failed
        ack = {
            "device_id": DEVICE_ID,
            "command_id": command_id,
            "action": action,
            "status": status,
        }
        client.publish(ACK_TOPIC, json.dumps(ack), qos=1)
        print(f"[{DEVICE_ID}] Sent ACK: {status}")

    except json.JSONDecodeError:
        print(f"[{DEVICE_ID}] Invalid JSON in command")
    except Exception as e:
        print(f"[{DEVICE_ID}] Error: {e}")


def send_heartbeat(client):
    heartbeat = {
        "device_id": DEVICE_ID,
        "cpu_percent": 23.5,
        "temperature": 45.2,
        "memory_percent": 62.1,
        "disk_percent": 34.0,
        "uptime_seconds": int(time.time()) % 100000,
        "cameras": [
            {"id": "CAM-001-L", "status": "ACTIVE"},
            {"id": "CAM-001-R", "status": "ACTIVE"},
        ],
    }
    client.publish(HEARTBEAT_TOPIC, json.dumps(heartbeat), qos=1)
    print(f"[{DEVICE_ID}] Heartbeat sent")


# Connect
client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"edge-{DEVICE_ID}",
    protocol=mqtt.MQTTv5,
)
client.username_pw_set(USERNAME, PASSWORD)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()

print(f"\n{'='*50}")
print(f"  Mock Edge Device: {DEVICE_ID}")
print(f"  Broker: {BROKER}:{PORT}")
print(f"  Heartbeat every 10s")
print(f"  Ctrl+C to stop")
print(f"{'='*50}\n")

try:
    while True:
        send_heartbeat(client)
        time.sleep(10)
except KeyboardInterrupt:
    print(f"\n[{DEVICE_ID}] Shutting down...")
finally:
    client.loop_stop()
    client.disconnect()
