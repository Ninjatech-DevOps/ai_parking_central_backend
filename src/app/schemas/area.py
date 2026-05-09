import uuid
from typing import Optional

from src.app.schemas.base import BaseSchema, BaseResponse


class AreaCreate(BaseSchema):
    name: str
    city_id: uuid.UUID
    taluka_id: Optional[uuid.UUID] = None
    village_id: Optional[uuid.UUID] = None


class AreaUpdate(BaseSchema):
    name: Optional[str] = None
    city_id: Optional[uuid.UUID] = None
    taluka_id: Optional[uuid.UUID] = None
    village_id: Optional[uuid.UUID] = None


class AreaResponse(BaseResponse):
    name: str
    city_id: uuid.UUID
    taluka_id: Optional[uuid.UUID]
    village_id: Optional[uuid.UUID]


class AreaFilter(BaseSchema):
    name: Optional[str] = None
    city_id: Optional[uuid.UUID] = None
    taluka_id: Optional[uuid.UUID] = None
    village_id: Optional[uuid.UUID] = None
