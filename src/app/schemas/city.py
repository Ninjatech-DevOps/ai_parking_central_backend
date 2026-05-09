import uuid
from typing import Optional

from src.app.schemas.base import BaseSchema, BaseResponse


class CityCreate(BaseSchema):
    name: str
    state_id: uuid.UUID


class CityUpdate(BaseSchema):
    name: Optional[str] = None
    state_id: Optional[uuid.UUID] = None


class CityResponse(BaseResponse):
    name: str
    state_id: uuid.UUID


class CityFilter(BaseSchema):
    name: Optional[str] = None
    state_id: Optional[uuid.UUID] = None
