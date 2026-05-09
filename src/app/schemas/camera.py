import uuid
from typing import List, Optional

from src.app.core.constants import CameraStatus
from src.app.schemas.base import BaseSchema, BaseResponse


class CameraCreate(BaseSchema):
    device_id: uuid.UUID
    position_label: str
    status: CameraStatus = CameraStatus.ACTIVE
    is_active: bool = True
    slot_ids: Optional[List[uuid.UUID]] = None


class CameraUpdate(BaseSchema):
    position_label: Optional[str] = None
    status: Optional[CameraStatus] = None
    is_active: Optional[bool] = None
    slot_ids: Optional[List[uuid.UUID]] = None


class CameraResponse(BaseResponse):
    device_id: uuid.UUID
    position_label: str
    status: str
    is_active: bool
    slot_ids: Optional[List[uuid.UUID]]


class CameraFilter(BaseSchema):
    device_id: Optional[uuid.UUID] = None
    status: Optional[CameraStatus] = None
    is_active: Optional[bool] = None
