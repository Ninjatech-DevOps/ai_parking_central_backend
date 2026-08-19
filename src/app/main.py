import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.app.api.v1 import api_v1_router
from src.app.core.config import settings
from src.app.core.logging import setup_logging
from src.app.exceptions.base import AppException
from src.app.exceptions.handler import app_exception_handler, unhandled_exception_handler
from src.app.middleware.logging import LoggingMiddleware
from src.app.mqtt.client import start_mqtt, stop_mqtt
from src.app.vehicle_counter.db import init_vehicle_counter_db
from src.app.vehicle_counter.routes import STATIC_DIR as VEHICLE_COUNTER_STATIC_DIR
from src.app.vehicle_counter.routes import router as vehicle_counter_router

logger = logging.getLogger("ai_parking")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting %s v%s [%s]", settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV)

    start_mqtt()
    logger.info("MQTT client started")

    if settings.VEHICLE_COUNTER_ENABLED:
        await init_vehicle_counter_db()

    yield

    stop_mqtt()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.APP_DEBUG else None,
    redoc_url="/api/redoc" if settings.APP_DEBUG else None,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.APP_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Routes
app.include_router(api_v1_router)

if settings.VEHICLE_COUNTER_ENABLED:
    app.include_router(vehicle_counter_router)
    # Mounted at a strict sub-path: a mount on the bare /vehicle-counter prefix
    # would swallow /vehicle-counter/api/* before the router ever sees it.
    app.mount(
        "/vehicle-counter/static",
        StaticFiles(directory=VEHICLE_COUNTER_STATIC_DIR),
        name="vehicle_counter_static",
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy 1", "version": settings.APP_VERSION}
