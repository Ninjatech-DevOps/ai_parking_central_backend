from src.app.models.state import State
from src.app.models.city import City
from src.app.models.taluka import Taluka
from src.app.models.village import Village
from src.app.models.area import Area
from src.app.models.location import Location
from src.app.models.floor import Floor
from src.app.models.zone import Zone
from src.app.models.parking_slot import ParkingSlot
from src.app.models.slot_event import SlotEvent
from src.app.models.device import Device
from src.app.models.camera import Camera
from src.app.models.device_telemetry import DeviceTelemetry
from src.app.models.device_command import DeviceCommand
from src.app.models.ota_deployment import OTADeployment
from src.app.models.user import User
from src.app.models.role import Role
from src.app.models.permission import Permission
from src.app.models.role_permission import RolePermission
from src.app.models.user_role import UserRole
from src.app.models.user_scope import UserScope
from src.app.models.alert_rule import AlertRule
from src.app.models.alert_event import AlertEvent
from src.app.models.notification_preference import NotificationPreference
from src.app.models.notification_log import NotificationLog
from src.app.models.shared_link import SharedLink
from src.app.models.anpr_camera_config import AnprCameraConfig
from src.app.models.anpr_record import AnprRecord
from src.app.models.anpr_session import AnprSession
from src.app.models.parking_scan import ParkingScan

__all__ = [
    "State", "City", "Taluka", "Village", "Area",
    "Location", "Floor", "Zone", "ParkingSlot", "SlotEvent",
    "Device", "Camera", "DeviceTelemetry", "DeviceCommand", "OTADeployment",
    "User", "Role", "Permission", "RolePermission", "UserRole", "UserScope",
    "AlertRule", "AlertEvent", "NotificationPreference", "NotificationLog",
    "SharedLink",
    "AnprCameraConfig", "AnprRecord", "AnprSession",
    "ParkingScan",
]
