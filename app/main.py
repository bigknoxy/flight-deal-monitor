"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select as sqlmodel_select

from app.alert import telegram_bot
from app.config import config
from app.database import close_db, get_session, init_db
from app.models.flight import AlertHistory, FlightDeal
from app.scheduler import get_scheduler_status, setup_jobs, shutdown_scheduler, start_scheduler

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


class FlightDealResponse(BaseModel):
    """Flight deal response model."""

    id: int
    route_id: str
    origin: str
    destination: str
    departure_date: str
    airline: str
    flight_numbers: str
    original_price_usd: float
    current_price_usd: float
    price_drop_percent: float
    deal_type: str
    booking_url: str
    seen_at: datetime
    expired_at: datetime | None = None


class AlertHistoryResponse(BaseModel):
    """Alert history response model."""

    id: int
    flight_deal_id: int
    sent_at: datetime
    telegram_message_id: str | None = None
    status: str
    error_message: str | None = None
    flight_deal: FlightDealResponse | None = None


class AlertHistoryListResponse(BaseModel):
    """Alert history list response with pagination metadata."""

    alerts: list[AlertHistoryResponse]
    total: int
    limit: int
    offset: int


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
            "flash_sale_threshold": config.app.flash_sale_threshold,
            "mistake_fare_threshold": config.app.mistake_fare_threshold,
            "regular_sweep_interval": config.app.regular_sweep_interval,
            "mistake_sweep_interval": config.app.mistake_sweep_interval,
        },
        "env": {
            "amadeus_env": config.env.amadeus_env,
            "log_level": config.env.log_level,
        },
    }


@app.get("/alerts/history", response_model=AlertHistoryListResponse)
async def get_alert_history(
    start_date: str | None = Query(
        default=None,
        description="Filter alerts sent on or after this date (YYYY-MM-DD)",
    ),
    end_date: str | None = Query(
        default=None,
        description="Filter alerts sent on or before this date (YYYY-MM-DD)",
    ),
    deal_type: str | None = Query(
        default=None,
        description="Filter by deal type: 'flash_sale' or 'mistake_fare'",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of alerts to return (default: 50, max: 200)",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of alerts to skip for pagination (default: 0)",
    ),
    session: AsyncSession = Depends(get_session),
):
    """Get alert history with optional filtering and pagination.

    Returns a paginated list of alerts sent, optionally filtered by date range
    and deal type. Each alert includes the associated flight deal details.

    - **start_date**: Filter alerts sent on or after this date (YYYY-MM-DD)
    - **end_date**: Filter alerts sent on or before this date (YYYY-MM-DD)
    - **deal_type**: Filter by deal type ('flash_sale' or 'mistake_fare')
    - **limit**: Maximum number of alerts to return (default: 50, max: 200)
    - **offset**: Number of alerts to skip for pagination (default: 0)
    """
    # Build the base query with a join to FlightDeal for deal_type filtering
    query = (
        sqlmodel_select(AlertHistory, FlightDeal)
        .join(FlightDeal, AlertHistory.flight_deal_id == FlightDeal.id)
    )

    # Apply date filters
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
                tzinfo=UTC
            )
            query = query.where(AlertHistory.sent_at >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid start_date format. Use YYYY-MM-DD.",
            )

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                tzinfo=UTC,
                hour=23,
                minute=59,
                second=59,
            )
            query = query.where(AlertHistory.sent_at <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid end_date format. Use YYYY-MM-DD.",
            )

    # Apply deal_type filter
    if deal_type:
        if deal_type not in ("flash_sale", "mistake_fare"):
            raise HTTPException(
                status_code=400,
                detail="Invalid deal_type. Must be 'flash_sale' or 'mistake_fare'.",
            )
        query = query.where(FlightDeal.deal_type == deal_type)

    # Get total count for pagination
    count_query = (
        sqlmodel_select(func.count())
        .select_from(AlertHistory)
        .join(FlightDeal, AlertHistory.flight_deal_id == FlightDeal.id)
    )

    # Apply same filters to count query
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
        count_query = count_query.where(AlertHistory.sent_at >= start_dt)
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            tzinfo=UTC, hour=23, minute=59, second=59
        )
        count_query = count_query.where(AlertHistory.sent_at <= end_dt)
    if deal_type:
        count_query = count_query.where(FlightDeal.deal_type == deal_type)

    count_result = await session.execute(count_query)
    total = count_result.scalar_one()

    # Apply pagination and execute
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    rows = result.all()

    # Build response
    alerts = []
    for alert_row, deal_row in rows:
        alerts.append(
            AlertHistoryResponse(
                id=alert_row.id,
                flight_deal_id=alert_row.flight_deal_id,
                sent_at=alert_row.sent_at,
                telegram_message_id=alert_row.telegram_message_id,
                status=alert_row.status,
                error_message=alert_row.error_message,
                flight_deal=FlightDealResponse(
                    id=deal_row.id,
                    route_id=deal_row.route_id,
                    origin=deal_row.origin,
                    destination=deal_row.destination,
                    departure_date=deal_row.departure_date,
                    airline=deal_row.airline,
                    flight_numbers=deal_row.flight_numbers,
                    original_price_usd=deal_row.original_price_usd,
                    current_price_usd=deal_row.current_price_usd,
                    price_drop_percent=deal_row.price_drop_percent,
                    deal_type=deal_row.deal_type,
                    booking_url=deal_row.booking_url,
                    seen_at=deal_row.seen_at,
                    expired_at=deal_row.expired_at,
                ),
            )
        )

    return AlertHistoryListResponse(
        alerts=alerts,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/alerts/{alert_id}", response_model=AlertHistoryResponse)
async def get_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get details for a specific alert by ID.

    Returns the alert history entry along with the associated flight deal details.

    - **alert_id**: The ID of the alert to retrieve
    """
    query = (
        sqlmodel_select(AlertHistory, FlightDeal)
        .join(FlightDeal, AlertHistory.flight_deal_id == FlightDeal.id)
        .where(AlertHistory.id == alert_id)
    )
    result = await session.execute(query)
    row = result.first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Alert with ID {alert_id} not found",
        )

    alert_row, deal_row = row

    return AlertHistoryResponse(
        id=alert_row.id,
        flight_deal_id=alert_row.flight_deal_id,
        sent_at=alert_row.sent_at,
        telegram_message_id=alert_row.telegram_message_id,
        status=alert_row.status,
        error_message=alert_row.error_message,
        flight_deal=FlightDealResponse(
            id=deal_row.id,
            route_id=deal_row.route_id,
            origin=deal_row.origin,
            destination=deal_row.destination,
            departure_date=deal_row.departure_date,
            airline=deal_row.airline,
            flight_numbers=deal_row.flight_numbers,
            original_price_usd=deal_row.original_price_usd,
            current_price_usd=deal_row.current_price_usd,
            price_drop_percent=deal_row.price_drop_percent,
            deal_type=deal_row.deal_type,
            booking_url=deal_row.booking_url,
            seen_at=deal_row.seen_at,
            expired_at=deal_row.expired_at,
        ),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=config.env.log_level.lower(),
    )
