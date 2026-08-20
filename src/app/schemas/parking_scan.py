import uuid
from datetime import datetime
from typing import Optional

from src.app.schemas.base import BaseSchema


class ParkingScanResponse(BaseSchema):
    id: uuid.UUID
    device_id: uuid.UUID
    camera_id: uuid.UUID
    location_id: uuid.UUID
    city_id: Optional[uuid.UUID]
    image_url: Optional[str]
    car_occupied: int
    car_available: int
    car_total: int
    two_wheeler_occupied: int
    two_wheeler_available: int
    two_wheeler_total: int
    has_obstruction: bool
    recorded_at: datetime
    location_name: Optional[str] = None
    camera_label: Optional[str] = None
    device_name: Optional[str] = None

    model_config = {"from_attributes": True}


def build_parking_scan_response(scan) -> "ParkingScanResponse":
    """Hydrate the denormalized display fields from a ParkingScan ORM row.

    location/camera/device are all lazy="selectin" on the model, so they are
    already loaded — this only copies them onto the response.

    Every route returning scans must go through here: camera_label has no
    validator, so a route that forgets it silently returns null (which is
    exactly what the public shared-link endpoint used to do).
    """
    resp = ParkingScanResponse.model_validate(scan)
    if scan.location:
        resp.location_name = scan.location.name
    if scan.camera:
        resp.camera_label = scan.camera.position_label
    if scan.device:
        resp.device_name = getattr(scan.device, "device_id", None)
    return resp


class ParkingScanUpdate(BaseSchema):
    """Inline-edit fields — all optional, only send what changed."""
    car_occupied: Optional[int] = None
    car_available: Optional[int] = None
    car_total: Optional[int] = None
    two_wheeler_occupied: Optional[int] = None
    two_wheeler_available: Optional[int] = None
    two_wheeler_total: Optional[int] = None
    recorded_at: Optional[datetime] = None
