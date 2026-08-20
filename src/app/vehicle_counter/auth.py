"""Static-password authentication for the vehicle counter module.

One shared password from configuration, exchanged for a long-lived JWT. There
is no username, no user table, and no per-operator identity -- entries cannot
be attributed to an individual.

Deliberately separate from the main application's auth: this module issues its
own token with its own expiry, so changing it never affects admin sessions.
"""

import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt

from src.app.core.config import settings
from src.app.core.security import decode_token
from src.app.exceptions.base import UnauthorizedException

# Marks a token as belonging to this module. Both modules sign with the same
# JWT_SECRET_KEY, so without this claim a main-app access token would be
# accepted here.
TOKEN_TYPE = "vehicle_counter"

# Tokens carry no user identity; the subject is a fixed constant.
TOKEN_SUBJECT = "vehicle_counter"

# auto_error=False so a missing header raises our own 401 with the standard
# {success, detail} body rather than FastAPI's differently-shaped 403.
_bearer = HTTPBearer(auto_error=False)


def create_counter_token() -> str:
    """Issue a token valid for VEHICLE_COUNTER_TOKEN_EXPIRE_DAYS."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": TOKEN_SUBJECT,
        "type": TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(days=settings.VEHICLE_COUNTER_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def authenticate(password: str) -> str:
    """Check the password and return a token.

    compare_digest rather than ``==`` so a wrong password takes the same time
    regardless of how many leading characters happened to match.
    """
    expected = settings.VEHICLE_COUNTER_PASSWORD or ""
    supplied = password or ""
    if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise UnauthorizedException(detail="Incorrect password")
    return create_counter_token()


async def require_counter_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Dependency guarding every API route in this module."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedException(detail="Not authenticated")

    # decode_token returns {} for an expired token, a bad signature, and
    # malformed input alike -- all of which are simply "not authenticated".
    payload = decode_token(credentials.credentials)
    if not payload:
        raise UnauthorizedException(detail="Invalid or expired token")

    if payload.get("type") != TOKEN_TYPE:
        raise UnauthorizedException(detail="Invalid or expired token")

    return payload.get("sub", TOKEN_SUBJECT)
