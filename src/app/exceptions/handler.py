import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from src.app.exceptions.base import AppException

logger = logging.getLogger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        "AppException: status=%s detail=%s path=%s",
        exc.status_code,
        exc.detail,
        request.url.path,
    )
    content = {"success": False, "detail": exc.detail}
    if exc.errors:
        content["errors"] = exc.errors
    return JSONResponse(status_code=exc.status_code, content=content)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s: %s", request.url.path, str(exc))
    return JSONResponse(
        status_code=500,
        content={"success": False, "detail": "Internal server error"},
    )
