from typing import List, Optional

from pydantic import BaseModel


class SlotUpdate(BaseModel):
    """Payload from edge device for slot state changes."""
    slot_label: str
    state: str  # VEHICLE | EMPTY | OBSTRUCTED
    camera_id: Optional[str] = None


class SlotUpdateMessage(BaseModel):
    """Full MQTT message for slot updates."""
    device_id: str
    slots: List[SlotUpdate]
    timestamp: Optional[str] = None


class HeartbeatMessage(BaseModel):
    """Full MQTT message for device heartbeat."""
    device_id: str
    cpu_percent: Optional[float] = None
    temperature: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    uptime_seconds: Optional[float] = None
    cameras: Optional[List[dict]] = None  # [{"id": "CAM-001-L", "status": "ACTIVE"}]
    timestamp: Optional[str] = None


class DeviceAlertMessage(BaseModel):
    """Full MQTT message for device-originated alerts."""
    device_id: str
    alert_type: str  # CAMERA_FAILURE | SYSTEM_ERROR | HIGH_TEMP
    message: str
    severity: Optional[str] = "HIGH"
    timestamp: Optional[str] = None


class CommandAckMessage(BaseModel):
    """Full MQTT message for command acknowledgements."""
    device_id: str
    command_id: Optional[str] = None
    action: str
    status: str  # acknowledged | completed | failed
    error: Optional[str] = None
    timestamp: Optional[str] = None
