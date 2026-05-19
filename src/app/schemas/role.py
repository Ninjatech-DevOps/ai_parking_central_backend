import uuid
from typing import List, Optional

from src.app.schemas.base import BaseSchema, BaseResponse
from src.app.schemas.permission import PermissionResponse


class RoleCreate(BaseSchema):
    name: str
    description: Optional[str] = None
    permission_ids: Optional[List[uuid.UUID]] = None


class RoleUpdate(BaseSchema):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[List[uuid.UUID]] = None


class RoleResponse(BaseResponse):
    name: str
    description: Optional[str]
    is_system_role: bool
    permissions: List[PermissionResponse] = []
    user_count: int = 0
