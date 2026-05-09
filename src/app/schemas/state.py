import uuid
from typing import Optional

from src.app.schemas.base import BaseSchema, BaseResponse


class StateCreate(BaseSchema):
    name: str
    code: str
    country: str = "India"


class StateUpdate(BaseSchema):
    name: Optional[str] = None
    code: Optional[str] = None
    country: Optional[str] = None


class StateResponse(BaseResponse):
    name: str
    code: str
    country: str


class StateFilter(BaseSchema):
    name: Optional[str] = None
    code: Optional[str] = None
    country: Optional[str] = None
