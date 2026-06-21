"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from app.alert import telegram_bot
from app.config import config
from app.database import AsyncSessionLocal, close_db, init_db
from app.models.flight import FlightDeal
from app.scheduler import (
    get_scheduler_status,
    setup_jobs,
    shutdown_scheduler,
    start_scheduler,
)

# Configure logging
logging.basicConfig(
    level=config.env.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
async def root() -> dict:
    """Root endpoint."""
    return {
        "name": config.app.name,
        "version": config.app.version,
        "description": "Automated flight deal monitoring and alerting system",
    }


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    scheduler_status = get_scheduler_status()

    return HealthResponse(
        status="healthy" if scheduler_status["running"] else "unhealthy",
        scheduler_running=scheduler_status["running"],
        jobs=scheduler_status["jobs"],
        job_count=scheduler_status["job_count"],
    )


@app.get("/config")
async def get_config() -> dict:
    """Get current configuration (without secrets)."""
    return {
        "app": {
            "name": config.app.name,
            "version": config.app.version,
            "home_airports": config.app.home_airports,
            "destinations": config.app.destinations,
            "deal_thresholds": {
                "mistake_fare_percent": config.app.deal_thresholds.mistake_fare_percent,
                "deep_flash_percent": config.app.deal_thresholds.deep_flash_percent,
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


@app.get("/deals", response_model=dict)
async def list_deals(
    limit: int = 20,
    offset: int = 0,
    deal_type: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
) -> dict:
    """List recent flight deals with optional filtering."""
    async with AsyncSessionLocal() as session:
        query = select(FlightDeal).order_by(FlightDeal.seen_at.desc())

        if deal_type:
            query = query.where(FlightDeal.deal_type == deal_type)
        if origin:
            query = query.where(FlightDeal.origin == origin.upper())
        if destination:
            query = query.where(FlightDeal.destination == destination.upper())

        count_query = select(func.count()).select_from(query.subquery())
        total = await session.execute(count_query)
        total_count = total.scalar() or 0

        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        deals = result.scalars().all()

        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "deals": [
                {
                    "id": d.id,
                    "route_id": d.route_id,
                    "origin": d.origin,
                    "destination": d.destination,
                    "departure_date": d.departure_date,
                    "airline": d.airline,
                    "flight_numbers": d.flight_numbers,
                    "original_price_usd": d.original_price_usd,
                    "current_price_usd": d.current_price_usd,
                    "price_drop_percent": d.price_drop_percent,
                    "deal_type": d.deal_type,
                    "booking_url": d.booking_url,
                    "seen_at": d.seen_at.isoformat() if d.seen_at else None,
                }
                for d in deals
            ],
        }


@app.get("/deals/stats", response_model=dict)
async def deal_stats() -> dict:
    """Get deal statistics."""
    async with AsyncSessionLocal() as session:
        total_query = select(func.count()).select_from(FlightDeal)
        total_result = await session.execute(total_query)
        total = total_result.scalar() or 0

        type_query = (
            select(FlightDeal.deal_type, func.count())
            .group_by(FlightDeal.deal_type)
        )
        type_result = await session.execute(type_query)
        by_type = dict(type_result.all())

        route_query = (
            select(FlightDeal.origin, FlightDeal.destination, func.count())
            .group_by(FlightDeal.origin, FlightDeal.destination)
            .order_by(func.count().desc())
            .limit(10)
        )
        route_result = await session.execute(route_query)
        top_routes = [
            {"origin": o, "destination": d, "count": c}
            for o, d, c in route_result.all()
        ]

        return {
            "total_deals": total,
            "by_type": by_type,
            "top_routes": top_routes,
        }


@app.get("/deals/{deal_id}", response_model=dict)
async def get_deal(deal_id: int) -> dict:
    """Get a single flight deal by ID."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(FlightDeal).where(FlightDeal.id == deal_id)
        )
        deal = result.scalar_one_or_none()

        if not deal:
            raise HTTPException(status_code=404, detail="Deal not found")

        return {
            "id": deal.id,
            "route_id": deal.route_id,
            "origin": deal.origin,
            "destination": deal.destination,
            "departure_date": deal.departure_date,
            "airline": deal.airline,
            "flight_numbers": deal.flight_numbers,
            "original_price_usd": deal.original_price_usd,
            "current_price_usd": deal.current_price_usd,
            "price_drop_percent": deal.price_drop_percent,
            "deal_type": deal.deal_type,
            "booking_url": deal.booking_url,
            "seen_at": deal.seen_at.isoformat() if deal.seen_at else None,
            "expired_at": deal.expired_at.isoformat() if deal.expired_at else None,
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
