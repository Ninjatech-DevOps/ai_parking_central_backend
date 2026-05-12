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
    alert_event,
    notification_preference,
    role,
    report,
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
api_v1_router.include_router(alert_event.router)
api_v1_router.include_router(notification_preference.router)
api_v1_router.include_router(role.router)
api_v1_router.include_router(report.router)
