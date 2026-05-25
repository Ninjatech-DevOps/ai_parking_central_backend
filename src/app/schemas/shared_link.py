import uuid
from datetime import datetime
from typing import List, Optional

from src.app.core.constants import SharedLinkScopeType
from src.app.schemas.base import BaseSchema, BaseResponse
from src.app.schemas.camera import CanvasCamera


class SharedLinkCreate(BaseSchema):
    name: Optional[str] = None
    scope_type: SharedLinkScopeType
    scope_id: Optional[uuid.UUID] = None
    camera_ids: Optional[List[uuid.UUID]] = None
    expires_at: Optional[datetime] = None


class SharedLinkUpdate(BaseSchema):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


class SharedLinkResponse(BaseResponse):
    token: str
    name: Optional[str]
    scope_type: str
    scope_id: Optional[uuid.UUID]
    camera_ids: Optional[str]
    created_by_user_id: uuid.UUID
    expires_at: Optional[datetime]
    is_active: bool
    view_count: int


class PublicLocationData(BaseSchema):
    id: uuid.UUID
    name: str
    cameras: List[CanvasCamera]
    summary: dict


class PublicViewResponse(BaseSchema):
    name: Optional[str]
    scope_type: str
    locations: List[PublicLocationData]
    total_summary: dict
