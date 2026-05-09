import uuid
from typing import Optional

from src.app.core.constants import AlertSeverity, AlertTriggerType, ScopeType
from src.app.schemas.base import BaseSchema, BaseResponse


class AlertRuleCreate(BaseSchema):
    name: str
    trigger_type: AlertTriggerType
    condition: Optional[str] = None
    severity: AlertSeverity
    scope_type: Optional[ScopeType] = None
    scope_id: Optional[uuid.UUID] = None
    is_active: bool = True


class AlertRuleUpdate(BaseSchema):
    name: Optional[str] = None
    condition: Optional[str] = None
    severity: Optional[AlertSeverity] = None
    scope_type: Optional[ScopeType] = None
    scope_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None


class AlertRuleResponse(BaseResponse):
    name: str
    trigger_type: str
    condition: Optional[str]
    severity: str
    scope_type: Optional[str]
    scope_id: Optional[uuid.UUID]
    is_active: bool
