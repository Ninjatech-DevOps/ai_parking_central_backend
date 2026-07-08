from fastapi import APIRouter

from src.app.api.v1.routes import (
    auth,
    user,
    state,
    city,
    taluka,
    village,
    area,
    location,
    floor,
    zone,
    device,
    device_command,
    camera,
    parking_slot,
    slot_event,
    alert_event,
    notification_preference,
    notification,
    role,
    report,
    shared_link,
    public_view,
    public_occupancy,
    anpr_camera_config,
    anpr_record,
    anpr_session,
    anpr_dashboard,
    parking_history,
    demo_report,
)

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth.router)
api_v1_router.include_router(user.router)
api_v1_router.include_router(state.router)
api_v1_router.include_router(city.router)
api_v1_router.include_router(taluka.router)
api_v1_router.include_router(village.router)
api_v1_router.include_router(area.router)
api_v1_router.include_router(location.router)
api_v1_router.include_router(floor.router)
api_v1_router.include_router(zone.router)
api_v1_router.include_router(device.router)
api_v1_router.include_router(device_command.router)
api_v1_router.include_router(camera.router)
api_v1_router.include_router(parking_slot.router)
api_v1_router.include_router(slot_event.router)
api_v1_router.include_router(alert_event.router)
api_v1_router.include_router(notification_preference.router)
api_v1_router.include_router(notification.router)
api_v1_router.include_router(role.router)
api_v1_router.include_router(report.router, include_in_schema=False)
api_v1_router.include_router(shared_link.router)
api_v1_router.include_router(public_view.router)
api_v1_router.include_router(public_occupancy.router)
api_v1_router.include_router(anpr_camera_config.router)
api_v1_router.include_router(anpr_record.router)
api_v1_router.include_router(anpr_session.router)
api_v1_router.include_router(anpr_dashboard.router)
api_v1_router.include_router(parking_history.router)
api_v1_router.include_router(demo_report.router)
