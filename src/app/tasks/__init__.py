from src.app.tasks.slot_update import process_slot_update  # noqa: F401
from src.app.tasks.slot_event import process_slot_event  # noqa: F401
from src.app.tasks.heartbeat import process_heartbeat  # noqa: F401
from src.app.tasks.device_status import process_device_status  # noqa: F401
from src.app.tasks.command_ack import process_command_ack  # noqa: F401
from src.app.tasks.sync_camera import process_sync_camera, update_camera_snapshot  # noqa: F401
from src.app.tasks.sync_slots import process_sync_slots  # noqa: F401
from src.app.tasks.device import check_device_heartbeats, process_ota_deployment  # noqa: F401
from src.app.tasks.notifications import send_push_notification, send_email_notification, process_alert, dispatch_alert_notifications  # noqa: F401
from src.app.tasks.vehicle_event import process_vehicle_events  # noqa: F401
from src.app.tasks.anpr_record import process_anpr_record  # noqa: F401
from src.app.tasks.anpr_sync import process_anpr_config_sync  # noqa: F401
from src.app.tasks.parking_scan import create_parking_scan  # noqa: F401
