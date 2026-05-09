import uuid
from typing import List, Optional

from pydantic import EmailStr

from src.app.core.constants import ScopeType
from src.app.schemas.base import BaseSchema, BaseResponse


class UserCreate(BaseSchema):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    password: str
    role_ids: Optional[List[uuid.UUID]] = None
    scopes: Optional[List["UserScopeAssign"]] = None


class UserUpdate(BaseSchema):
    name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    fcm_tokens: Optional[List[str]] = None


class UserResponse(BaseResponse):
    email: str
    name: str
    phone: Optional[str]
    is_active: bool
    fcm_tokens: Optional[List[str]]


class UserScopeAssign(BaseSchema):
    scope_type: ScopeType
    scope_id: uuid.UUID


class UserFilter(BaseSchema):
    email: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None
    role_id: Optional[uuid.UUID] = None


class ChangePassword(BaseSchema):
    current_password: str
    new_password: str
