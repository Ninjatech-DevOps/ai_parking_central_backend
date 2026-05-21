from typing import List, Optional

from pydantic import BaseModel


class SlotSnapshot(BaseModel):
    """Single slot in a full-state snapshot (/slots topic)."""
    slot_label: str
    state: str  # VEHICLE | EMPTY | OBSTRUCTED
    slot_type: Optional[str] = None
    detected_vehicle_type: Optional[str] = None


class SlotSnapshotMessage(BaseModel):
    """Full MQTT message for slot snapshot (reconciliation)."""
    device_id: str
    camera_id: str
    slots: List[SlotSnapshot]
    timestamp: Optional[float] = None


class SlotChange(BaseModel):
    """Single slot change in an event (/events topic)."""
    slot_label: str
    state: str  # VEHICLE | EMPTY | OBSTRUCTED
    confidence: Optional[float] = None
    slot_type: Optional[str] = None
    detected_vehicle_type: Optional[str] = None
    is_mismatched: bool = False


class SlotEventMessage(BaseModel):
    """Full MQTT message for slot change events (real-time diffs)."""
    device_id: str
    camera_id: str
    changes: List[SlotChange]
    timestamp: Optional[float] = None


class HeartbeatMessage(BaseModel):
    """Full MQTT message for device heartbeat telemetry (/heartbeat topic)."""
    device_id: str
    cpu_percent: Optional[float] = None
    temperature: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    uptime_seconds: Optional[float] = None
    cameras: Optional[List[dict]] = None
    timestamp: Optional[float] = None


class DeviceStatusMessage(BaseModel):
    """Full MQTT message for device online/offline (/status topic + LWT)."""
    device_id: str
    status: str  # online | offline
    timestamp: Optional[float] = None


class DeviceAlertMessage(BaseModel):
    """Full MQTT message for device-originated alerts."""
    device_id: str
    alert_type: str  # CAMERA_FAILURE | SYSTEM_ERROR | HIGH_TEMP
    message: str
    severity: Optional[str] = "HIGH"
    timestamp: Optional[float] = None


class CommandAckMessage(BaseModel):
    """Full MQTT message for command acknowledgements."""
    device_id: str
    command_id: Optional[str] = None
    action: str
    status: str  # acknowledged | completed | failed
    error: Optional[str] = None
    timestamp: Optional[float] = None
