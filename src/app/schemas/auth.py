from typing import Optional

from pydantic import EmailStr

from src.app.schemas.base import BaseSchema


class LoginRequest(BaseSchema):
    email: EmailStr
    password: str


class TokenResponse(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseSchema):
    refresh_token: str


class TokenPayload(BaseSchema):
    sub: str
    exp: Optional[int] = None
    type: str = "access"
