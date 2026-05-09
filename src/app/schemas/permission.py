from typing import Optional

from src.app.schemas.base import BaseSchema, BaseResponse


class PermissionCreate(BaseSchema):
    resource: str
    action: str


class PermissionResponse(BaseResponse):
    resource: str
    action: str


class PermissionFilter(BaseSchema):
    resource: Optional[str] = None
    action: Optional[str] = None
