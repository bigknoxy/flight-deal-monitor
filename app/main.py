"""FastAPI application entry point."""

import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from pydantic import BaseModel

from app.alert import telegram_bot
from app.config import config
from app.database import init_db, close_db
from app.logging_config import configure_logging, request_id, correlation_id, clear_context
from app.scheduler import start_scheduler, shutdown_scheduler, setup_jobs, get_scheduler_status

# Configure structured JSON logging
configure_logging(
    log_level=config.env.log_level,
    log_format=config.env.log_format,
)
logger = structlog.get_logger()


class RequestIdMiddleware:
    """ASGI middleware that assigns a request_id and correlation_id
    to every incoming HTTP request and ensures they appear in all log entries.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        req_id = str(uuid.uuid4())[:12]
        corr_id = correlation_id.get() or str(uuid.uuid4())[:16]
        request_id.set(req_id)
        correlation_id.set(corr_id)

        # Inject request_id into response headers for client-side tracing
        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-request-id"] = req_id.encode()
                headers[b"x-correlation-id"] = corr_id.encode()
                message["headers"] = list(headers.items())
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            clear_context()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("starting_flight_deal_monitor")
    await init_db()
    await telegram_bot.test_connection()
    setup_jobs()
    start_scheduler()
    logger.info("flight_deal_monitor_started")

    yield

    # Shutdown
    logger.info("shutting_down_flight_deal_monitor")
    shutdown_scheduler()
    await close_db()
    logger.info("flight_deal_monitor_shutdown_complete")


# Create FastAPI app
app = FastAPI(
    title="Flight Deal Monitor",
    description="Automated flight deal monitoring and alerting system",
    version=config.app.version,
    lifespan=lifespan,
)

# Add request ID middleware
app.add_middleware(RequestIdMiddleware)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    scheduler_running: bool
    jobs: list
    job_count: int


@app.get("/", response_model=dict)
async def root(request: Request):
    """Root endpoint."""
    logger.info("root_endpoint_accessed")
    return {
        "name": config.app.name,
        "version": config.app.version,
        "description": "Automated flight deal monitoring and alerting system",
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    scheduler_status = get_scheduler_status()

    logger.info(
        "health_check",
        status="healthy" if scheduler_status["running"] else "unhealthy",
        job_count=scheduler_status["job_count"],
    )

    return HealthResponse(
        status="healthy" if scheduler_status["running"] else "unhealthy",
        scheduler_running=scheduler_status["running"],
        jobs=scheduler_status["jobs"],
        job_count=scheduler_status["job_count"],
    )


@app.get("/config")
async def get_config():
    """Get current configuration (without secrets)."""
    return {
        "app": {
            "name": config.app.name,
            "version": config.app.version,
            "home_airports": config.app.home_airports,
            "destinations": config.app.destinations,
            "flash_sale_threshold": config.app.flash_sale_threshold,
            "mistake_fare_threshold": config.app.mistake_fare_threshold,
            "regular_sweep_interval": config.app.regular_sweep_interval,
            "mistake_sweep_interval": config.app.mistake_sweep_interval,
        },
        "env": {
            "amadeus_env": config.env.amadeus_env,
            "log_level": config.env.log_level,
            "log_format": config.env.log_format,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=config.env.log_level.lower(),
    )
