import uuid
from typing import List, Optional

from src.app.core.constants import CameraStatus, CameraType
from src.app.schemas.base import BaseSchema, BaseResponse


class CameraCreate(BaseSchema):
    device_id: uuid.UUID
    position_label: str
    source: Optional[str] = "0"
    camera_type: Optional[CameraType] = CameraType.USB
    detection_interval: Optional[float] = 30.0
    status: CameraStatus = CameraStatus.ACTIVE
    is_active: bool = True


class CameraUpdate(BaseSchema):
    position_label: Optional[str] = None
    source: Optional[str] = None
    camera_type: Optional[CameraType] = None
    detection_interval: Optional[float] = None
    status: Optional[CameraStatus] = None
    is_active: Optional[bool] = None


class CameraResponse(BaseResponse):
    device_id: uuid.UUID
    position_label: str
    source: Optional[str]
    camera_type: Optional[str]
    detection_interval: Optional[float]
    status: str
    is_active: bool
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None
    snapshot_path: Optional[str] = None


# Slot config pushed from client
class SlotPositionItem(BaseSchema):
    slot_id: uuid.UUID
    polygon_coords: Optional[str] = None
    pos_x1: int
    pos_y1: int
    pos_x2: int
    pos_y2: int


class SlotConfigRequest(BaseSchema):
    slots: List[SlotPositionItem]


# Canvas data response
class CanvasSlot(BaseSchema):
    id: uuid.UUID
    label: str
    state: str
    slot_type: str
    detected_vehicle_type: Optional[str] = None
    is_mismatched: bool = False
    polygon_coords: Optional[str]
    pos_x1: Optional[int]
    pos_y1: Optional[int]
    pos_x2: Optional[int]
    pos_y2: Optional[int]


class CanvasCamera(BaseSchema):
    id: uuid.UUID
    device_id: uuid.UUID
    position_label: str
    status: str
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None
    slots: List[CanvasSlot]


class CanvasResponse(BaseSchema):
    location_id: uuid.UUID
    location_name: str
    cameras: List[CanvasCamera]
