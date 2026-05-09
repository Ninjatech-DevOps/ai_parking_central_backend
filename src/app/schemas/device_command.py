import uuid
from datetime import datetime
from typing import Optional

from src.app.core.constants import CommandType, CommandStatus
from src.app.schemas.base import BaseSchema, BaseResponse


class DeviceCommandCreate(BaseSchema):
    device_id: uuid.UUID
    command_type: CommandType
    payload: Optional[str] = None


class DeviceCommandResponse(BaseResponse):
    device_id: uuid.UUID
    command_type: str
    payload: Optional[str]
    status: str
    sent_by: Optional[uuid.UUID]
    sent_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]


class DeviceCommandFilter(BaseSchema):
    device_id: Optional[uuid.UUID] = None
    command_type: Optional[CommandType] = None
    status: Optional[CommandStatus] = None
