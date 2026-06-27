import uuid
from typing import Optional

from src.app.core.constants import AnprDirection
from src.app.schemas.base import BaseSchema, BaseResponse


class AnprCameraConfigCreate(BaseSchema):
    camera_id: uuid.UUID
    roi_coords: Optional[str] = None
    trigger_line: Optional[str] = None
    direction: AnprDirection = AnprDirection.IN
    is_active: bool = True


class AnprCameraConfigUpdate(BaseSchema):
    roi_coords: Optional[str] = None
    trigger_line: Optional[str] = None
    direction: Optional[AnprDirection] = None
    is_active: Optional[bool] = None


class AnprCameraConfigResponse(BaseResponse):
    camera_id: uuid.UUID
    roi_coords: Optional[str]
    trigger_line: Optional[str]
    direction: str
    is_active: bool
