"""FastAPI application entry point."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from passlib.hash import bcrypt
from pydantic import BaseModel
from sqlalchemy import func, select

from app.alert import telegram_bot
from app.bot import bot_handler
from app.config import config
from app.database import AsyncSessionLocal, close_db, init_db
from app.job_lifecycle import reconcile_stale_job_runs
from app.models.flight import FlightDeal
from app.models.job import JobRun
from app.models.user import User
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.scheduler import (
    get_scheduler_status,
    setup_jobs,
    shutdown_scheduler,
    start_scheduler,
)
from app.utils.price_analysis import get_price_history

# Configure logging
logging.basicConfig(
    level=config.env.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _seed_admin_user() -> None:
    """Bootstrap an admin account when registration is disabled.

    If REGISTRATION_DISABLED is set and no users exist yet, create the admin
    from ADMIN_EMAIL / ADMIN_PASSWORD so the operator is never locked out of a
    fresh, locked-down deployment.
    """
    if not config.env.registration_disabled:
        return
    if not (config.env.admin_email and config.env.admin_password):
        logger.warning(
            "Registration is disabled but ADMIN_EMAIL/ADMIN_PASSWORD are not "
            "set; no admin will be created. The app will be inaccessible until "
            "an account is seeded manually."
        )
        return

    async with AsyncSessionLocal() as session:
        count = await session.execute(select(func.count()).select_from(User))
        if (count.scalar() or 0) > 0:
            return
        admin = User(
            email=config.env.admin_email,
            password_hash=bcrypt.hash(config.env.admin_password),
        )
        session.add(admin)
        await session.commit()
        logger.info(f"Seeded admin user: {config.env.admin_email}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info("Starting flight deal monitor...")
    await init_db()
    # Recover JobRun rows orphaned by a previous crash/SIGKILL so the dashboard
    # run history stays truthful. Best-effort: never blocks boot on a DB hiccup.
    try:
        await reconcile_stale_job_runs()
    except Exception as e:
        logger.warning(f"JobRun reconciliation skipped (continuing): {e}")
    # Admin seed is best-effort: a DB hiccup during seeding must never crash
    # startup (the app still boots and serves, auth just has no seeded admin).
    try:
        await _seed_admin_user()
    except Exception as e:
        logger.warning(f"Admin user seed skipped (continuing): {e}")

    # Telegram is optional. A missing/failed bot token must not crash startup;
    # the scheduler and API still work (alerts simply won't deliver).
    if config.env.telegram_bot_token:
        try:
            await telegram_bot.test_connection()
        except Exception as e:
            logger.warning(f"Telegram test connection failed (continuing): {e}")
    else:
        logger.info("No TELEGRAM_BOT_TOKEN set; skipping Telegram boot check.")

    setup_jobs()
    start_scheduler()
    # Start interactive Telegram bot polling (best-effort, never blocks boot).
    try:
        await bot_handler.start_polling()
    except Exception as e:
        logger.warning(f"Telegram bot polling start skipped (continuing): {e}")
    logger.info("Flight deal monitor started successfully")

    yield

    # Shutdown
    logger.info("Shutting down flight deal monitor...")
    await bot_handler.stop_polling()
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

# Mount static files and dashboard routes
app.mount(
    "/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static"
)
app.include_router(auth_router)
app.include_router(dashboard_router)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    scheduler_running: bool
    jobs: list
    job_count: int


@app.get("/")
async def root() -> RedirectResponse:
    """Root endpoint redirects to dashboard."""
    return RedirectResponse(url="/dashboard")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint.

    Returns 503 (not 200) when the scheduler is not running OR a JobRun is
    stuck ``running`` past the reconcile window — i.e. the scheduler process is
    alive but wedged and not self-healing. This lets an orchestrator actually
    restart a dead worker instead of believing the monitor is healthy forever.
    """
    scheduler_status = get_scheduler_status()
    healthy = scheduler_status["running"]

    if healthy:
        try:
            cutoff = datetime.utcnow() - timedelta(
                seconds=3600  # mirrors scheduler_jobs.RECONCILE_MAX_AGE_SECONDS
            )
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(JobRun)
                    .where(JobRun.completed_at.is_(None))
                    .where(JobRun.started_at < cutoff)
                    .limit(1)
                )
                if result.scalar_one_or_none() is not None:
                    healthy = False
        except Exception:
            # If we can't introspect, trust the scheduler's own running flag.
            pass

    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content=HealthResponse(
            status="healthy" if healthy else "unhealthy",
            scheduler_running=scheduler_status["running"],
            jobs=scheduler_status["jobs"],
            job_count=scheduler_status["job_count"],
        ).model_dump(),
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
            "long_weekend": {
                "enabled": config.app.long_weekend.enabled,
                "interval_minutes": config.app.long_weekend.interval_minutes,
                "look_ahead_months": config.app.long_weekend.look_ahead_months,
            },
            "flexible_dates": {
                "enabled": config.app.flexible_dates.enabled,
                "range_days": config.app.flexible_dates.range_days,
            },
            "multi_city": {
                "enabled": config.app.multi_city.enabled,
                "max_stops": config.app.multi_city.max_stops,
            },
        },
        "env": {
            "amadeus_env": config.env.amadeus_env,
            "log_level": config.env.log_level,
        },
    }


VALID_DEAL_TYPES = {"mistake_fare", "flash_sale", "deep_flash"}


@app.get("/deals", response_model=dict)
async def list_deals(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    deal_type: str | None = Query(None),
    origin: str | None = Query(None),
    destination: str | None = Query(None),
) -> dict:
    """List recent flight deals with optional filtering."""
    if deal_type and deal_type not in VALID_DEAL_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid deal_type '{deal_type}'. Must be one of: {', '.join(sorted(VALID_DEAL_TYPES))}",
        )
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

        type_query = select(FlightDeal.deal_type, func.count()).group_by(
            FlightDeal.deal_type
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


@app.get("/deals/history", response_model=dict)
async def deal_price_history(
    origin: str = Query(...),
    destination: str = Query(...),
    days: int = Query(90, ge=1, le=365),
) -> dict:
    """Get price history for a route."""
    async with AsyncSessionLocal() as session:
        return await get_price_history(
            session, origin.upper(), destination.upper(), days
        )


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

    # reload defaults OFF: running multiple app instances (or a reloader +
    # scheduler) would spawn duplicate sweeps. Enable only for local dev via
    # APP_RELOAD=true.
    reload = os.environ.get("APP_RELOAD", "false").lower() == "true"
    port = int(os.environ.get("APP_PORT", "8787"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level=config.env.log_level.lower(),
    )
