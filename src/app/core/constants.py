import enum


class SlotState(str, enum.Enum):
    VEHICLE = "VEHICLE"
    EMPTY = "EMPTY"
    OBSTRUCTED = "OBSTRUCTED"


class DeviceStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UPDATING = "UPDATING"
    MAINTENANCE = "MAINTENANCE"


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
    REGIONAL_MANAGER = "REGIONAL_MANAGER"
    LOCATION_MANAGER = "LOCATION_MANAGER"
    OPERATOR = "OPERATOR"
    TECHNICIAN = "TECHNICIAN"


class ScopeType(str, enum.Enum):
    STATE = "STATE"
    CITY = "CITY"
    AREA = "AREA"
    LOCATION = "LOCATION"
    ZONE = "ZONE"


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
    CAMERA_FAILURE = "CAMERA_FAILURE"
    HIGH_OCCUPANCY = "HIGH_OCCUPANCY"
    OBSTRUCTION_PATTERN = "OBSTRUCTION_PATTERN"
    DEVICE_HIGH_TEMP = "DEVICE_HIGH_TEMP"
    SYSTEM_ERROR = "SYSTEM_ERROR"


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
    CMD_CONFIG = "cmd/{device_id}/config"
    CMD_SHELL = "cmd/{device_id}/shell"
    CMD_SNAPSHOT = "cmd/{device_id}/snapshot"

    # Config sync from devices
    SYNC_CAMERA = "parking/{device_id}/sync/camera"
    SYNC_SLOTS = "parking/{device_id}/sync/slots"

    # Wildcard subscriptions for central server
    ALL_SLOTS = "parking/+/slots"
    ALL_EVENTS = "parking/+/events"
    ALL_HEARTBEATS = "parking/+/heartbeat"
    ALL_STATUS = "parking/+/status"
    ALL_ALERTS = "parking/+/alerts"
    ALL_ACKS = "parking/+/ack"
    ALL_SYNC = "parking/+/sync/#"


# Permissions
class Permission:
    DEVICES_VIEW = "devices:view"
    DEVICES_RESTART = "devices:restart"
    DEVICES_UPDATE = "devices:update"
    DEVICES_SHELL = "devices:shell"

    LOCATIONS_VIEW = "locations:view"
    LOCATIONS_MANAGE = "locations:manage"

    SLOTS_VIEW = "slots:view"

    USERS_VIEW = "users:view"
    USERS_CREATE = "users:create"
    USERS_EDIT = "users:edit"
    USERS_DELETE = "users:delete"

    ALERTS_VIEW = "alerts:view"
    ALERTS_ACKNOWLEDGE = "alerts:acknowledge"
    ALERTS_CONFIGURE = "alerts:configure"

    REPORTS_VIEW = "reports:view"
    REPORTS_EXPORT = "reports:export"

    NOTIFICATIONS_CONFIGURE = "notifications:configure"

    OTA_DEPLOY = "ota:deploy"
    OTA_ROLLBACK = "ota:rollback"
