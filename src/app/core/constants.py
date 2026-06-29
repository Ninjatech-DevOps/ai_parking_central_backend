import enum


class SlotState(str, enum.Enum):
    VEHICLE = "VEHICLE"
    EMPTY = "EMPTY"
    OBSTRUCTED = "OBSTRUCTED"


class SlotType(str, enum.Enum):
    CAR = "CAR"
    TWO_WHEELER = "TWO_WHEELER"
    GENERAL = "GENERAL"


class VehicleType(str, enum.Enum):
    CAR = "CAR"
    TWO_WHEELER = "TWO_WHEELER"


class AnprDirection(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class DeviceStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UPDATING = "UPDATING"
    MAINTENANCE = "MAINTENANCE"


class CameraType(str, enum.Enum):
    CSI = "CSI"
    RTSP = "RTSP"
    USB = "USB"


class CameraModuleType(str, enum.Enum):
    AI_PARKING = "AI_PARKING"
    ANPR = "ANPR"


class CameraStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    FAILED = "FAILED"


class LocationType(str, enum.Enum):
    MALL = "MALL"
    STREET = "STREET"
    OPEN = "OPEN"
    COMMERCIAL = "COMMERCIAL"
    RESIDENTIAL = "RESIDENTIAL"


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"


class ScopeType(str, enum.Enum):
    STATE = "STATE"
    CITY = "CITY"
    AREA = "AREA"
    LOCATION = "LOCATION"
    ZONE = "ZONE"


class SharedLinkScopeType(str, enum.Enum):
    CITY = "CITY"
    TALUKA = "TALUKA"
    VILLAGE = "VILLAGE"
    AREA = "AREA"
    LOCATION = "LOCATION"
    CAMERA = "CAMERA"


class AlertSeverity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlertStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class AlertTriggerType(str, enum.Enum):
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    DEVICE_ONLINE = "DEVICE_ONLINE"
    CAMERA_FAILURE = "CAMERA_FAILURE"
    HIGH_OCCUPANCY = "HIGH_OCCUPANCY"
    OBSTRUCTION_PATTERN = "OBSTRUCTION_PATTERN"
    DEVICE_HIGH_TEMP = "DEVICE_HIGH_TEMP"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    VEHICLE_TYPE_MISMATCH = "VEHICLE_TYPE_MISMATCH"


class NotificationChannel(str, enum.Enum):
    PUSH = "PUSH"
    EMAIL = "EMAIL"
    SMS = "SMS"
    IN_APP = "IN_APP"


class OTAStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"


class RolloutStrategy(str, enum.Enum):
    ALL_AT_ONCE = "ALL_AT_ONCE"
    CANARY = "CANARY"
    ROLLING = "ROLLING"
    BY_LOCATION = "BY_LOCATION"


class CommandType(str, enum.Enum):
    RESTART = "RESTART"
    UPDATE = "UPDATE"
    ROLLBACK = "ROLLBACK"
    VERSION = "VERSION"
    CONFIG = "CONFIG"
    SHELL = "SHELL"
    SNAPSHOT = "SNAPSHOT"


class CommandStatus(str, enum.Enum):
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


# MQTT Topic Patterns
class MQTTTopics:
    SLOT_SNAPSHOT = "parking/{device_id}/slots"
    SLOT_EVENTS = "parking/{device_id}/events"
    HEARTBEAT = "parking/{device_id}/heartbeat"
    DEVICE_STATUS = "parking/{device_id}/status"
    DEVICE_ALERT = "parking/{device_id}/alerts"
    DEVICE_ACK = "parking/{device_id}/ack"

    CMD_RESTART = "cmd/{device_id}/restart"
    CMD_UPDATE = "cmd/{device_id}/update"
    CMD_ROLLBACK = "cmd/{device_id}/rollback"
    CMD_VERSION = "cmd/{device_id}/version"
    CMD_CONFIG = "cmd/{device_id}/config"
    CMD_SHELL = "cmd/{device_id}/shell"
    CMD_SNAPSHOT = "cmd/{device_id}/snapshot"
    CMD_CONFIG_CAMERA = "cmd/{device_id}/config/camera"
    CMD_CONFIG_SLOTS = "cmd/{device_id}/config/slots"
    CMD_CALIBRATE = "cmd/{device_id}/calibrate"

    # Config sync from devices
    SYNC_CAMERA = "parking/{device_id}/sync/camera"
    SYNC_SLOTS = "parking/{device_id}/sync/slots"

    # Vehicle tracking events (multi-capacity zones)
    VEHICLE_EVENTS = "parking/{device_id}/vehicle_events"

    # ANPR topics
    ANPR_RECORD = "anpr/{device_id}/record"
    ANPR_SYNC_CONFIG = "anpr/{device_id}/sync/config"
    ANPR_CMD_CONFIG = "anpr/{device_id}/cmd/config"
    ANPR_ACK = "anpr/{device_id}/ack"

    # Parking scan (history row from client)
    PARKING_SCAN = "parking/{device_id}/scan"

    # Wildcard subscriptions for central server
    ALL_PARKING_SCANS = "parking/+/scan"
    ALL_SLOTS = "parking/+/slots"
    ALL_EVENTS = "parking/+/events"
    ALL_HEARTBEATS = "parking/+/heartbeat"
    ALL_STATUS = "parking/+/status"
    ALL_ALERTS = "parking/+/alerts"
    ALL_ACKS = "parking/+/ack"
    ALL_CMD_RESULTS = "parking/+/cmd/result"
    ALL_SYNC = "parking/+/sync/#"
    ALL_VEHICLE_EVENTS = "parking/+/vehicle_events"

    # ANPR wildcard subscriptions
    ALL_ANPR_RECORDS = "anpr/+/record"
    ALL_ANPR_SYNC = "anpr/+/sync/#"


# Permissions
class Permission:
    # Devices — CRUD + special actions
    DEVICES_VIEW = "devices:view"
    DEVICES_CREATE = "devices:create"
    DEVICES_EDIT = "devices:edit"
    DEVICES_DELETE = "devices:delete"
    DEVICES_RESTART = "devices:restart"
    DEVICES_UPDATE = "devices:update"       # Firmware/OTA push
    DEVICES_SHELL = "devices:shell"

    # Locations (includes floors, zones) — CRUD
    LOCATIONS_VIEW = "locations:view"
    LOCATIONS_CREATE = "locations:create"
    LOCATIONS_EDIT = "locations:edit"
    LOCATIONS_DELETE = "locations:delete"

    # Parking Slots — CRUD
    SLOTS_VIEW = "slots:view"
    SLOTS_CREATE = "slots:create"
    SLOTS_EDIT = "slots:edit"
    SLOTS_DELETE = "slots:delete"

    # Users — CRUD
    USERS_VIEW = "users:view"
    USERS_CREATE = "users:create"
    USERS_EDIT = "users:edit"
    USERS_DELETE = "users:delete"

    # Roles — CRUD
    ROLES_VIEW = "roles:view"
    ROLES_CREATE = "roles:create"
    ROLES_EDIT = "roles:edit"
    ROLES_DELETE = "roles:delete"

    # Alerts — CRUD + special
    ALERTS_VIEW = "alerts:view"
    ALERTS_CREATE = "alerts:create"
    ALERTS_EDIT = "alerts:edit"
    ALERTS_DELETE = "alerts:delete"
    ALERTS_ACKNOWLEDGE = "alerts:acknowledge"
    ALERTS_CONFIGURE = "alerts:configure"

    # Reports — view + export
    REPORTS_VIEW = "reports:view"
    REPORTS_EXPORT = "reports:export"

    # Notifications — CRUD
    NOTIFICATIONS_VIEW = "notifications:view"
    NOTIFICATIONS_CREATE = "notifications:create"
    NOTIFICATIONS_EDIT = "notifications:edit"
    NOTIFICATIONS_DELETE = "notifications:delete"
    NOTIFICATIONS_CONFIGURE = "notifications:configure"

    # OTA — deploy + rollback
    OTA_VIEW = "ota:view"
    OTA_DEPLOY = "ota:deploy"
    OTA_ROLLBACK = "ota:rollback"

    # ANPR — view + export
    ANPR_VIEW = "anpr:view"
    ANPR_CONFIGURE = "anpr:configure"
    ANPR_EXPORT = "anpr:export"

    # Shared Links — CRUD (super_admin only)
    SHARED_LINKS_VIEW = "shared_links:view"
    SHARED_LINKS_CREATE = "shared_links:create"
    SHARED_LINKS_EDIT = "shared_links:edit"
    SHARED_LINKS_DELETE = "shared_links:delete"
