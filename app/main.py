"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.alert import telegram_bot
from app.config import config
from app.database import init_db, close_db
from app.scheduler import start_scheduler, shutdown_scheduler, setup_jobs, get_scheduler_status

# Configure logging
logging.basicConfig(
    level=config.env.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting flight deal monitor...")
    await init_db()
    await telegram_bot.test_connection()
    setup_jobs()
    start_scheduler()
    logger.info("Flight deal monitor started successfully")

    yield

    # Shutdown
    logger.info("Shutting down flight deal monitor...")
    shutdown_scheduler()
    await close_db()
    logger.info("Flight deal monitor shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Flight Deal Monitor",
    description="Automated flight deal monitoring and alerting system",
    version=config.app.version,
    lifespan=lifespan,
)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    scheduler_running: bool
    jobs: list
    job_count: int


@app.get("/", response_model=dict)
async def root():
    """Root endpoint."""
    return {
        "name": config.app.name,
        "version": config.app.version,
        "description": "Automated flight deal monitoring and alerting system",
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    scheduler_status = get_scheduler_status()

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
            "deal_thresholds": {
                "mistake_fare_percent": config.app.deal_thresholds.mistake_fare_percent,
                "flash_sale_percent": config.app.deal_thresholds.flash_sale_percent,
            },
            "regular_sweep_interval": config.app.regular_sweep_interval,
            "mistake_sweep_interval": config.app.mistake_sweep_interval,
        },
        "env": {
            "amadeus_env": config.env.amadeus_env,
            "log_level": config.env.log_level,
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