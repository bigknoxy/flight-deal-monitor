"""Dashboard routes for the web UI."""

import os

import yaml
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from app.auth import require_login
from app.config import config
from app.database import AsyncSessionLocal
from app.models.flight import FlightDeal
from app.models.job import JobRun
from app.scheduler import get_scheduler_status
from app.templates import render

router = APIRouter()


def _get_route_config() -> dict:
    return {
        "home_airports": config.app.home_airports,
        "destinations": config.app.destinations,
        "long_weekend": {
            "enabled": config.app.long_weekend.enabled,
            "interval_minutes": config.app.long_weekend.interval_minutes,
            "look_ahead_months": config.app.long_weekend.look_ahead_months,
        },
    }


async def _get_deals(
    limit: int = 20,
    offset: int = 0,
    deal_type: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
) -> dict:
    """Get flight deals with optional filtering (reused from main.py)."""
    async with AsyncSessionLocal() as session:
        query = select(FlightDeal).order_by(FlightDeal.seen_at.desc())

        if deal_type:
            query = query.where(FlightDeal.deal_type == deal_type)
        if origin:
            query = query.where(FlightDeal.origin == origin.upper())
        if destination:
            query = query.where(FlightDeal.destination == destination.upper())

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total_count = total_result.scalar() or 0

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


async def _get_deal_stats() -> dict:
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


async def _get_config_display() -> dict:
    """Get config for display (without secrets)."""
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
            "route_multipliers": {
                "domestic": config.app.route_multipliers.domestic,
                "transatlantic": config.app.route_multipliers.transatlantic,
                "transpacific": config.app.route_multipliers.transpacific,
                "latin_america": config.app.route_multipliers.latin_america,
                "europe": config.app.route_multipliers.europe,
            },
            "max_results_per_route": config.app.max_results_per_route,
            "look_ahead_days": config.app.look_ahead_days,
            "min_price_usd": config.app.min_price_usd,
            "max_alerts_per_hour": config.app.max_alerts_per_hour,
            "cache_ttl_minutes": config.app.cache_ttl_minutes,
            "job_coalesce": config.app.job_coalesce,
        },
        "env": {
            "amadeus_env": config.env.amadeus_env,
            "log_level": config.env.log_level,
        },
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_index(
    request: Request,
    user: dict = Depends(require_login),
) -> HTMLResponse:
    """Dashboard overview page."""
    stats = await _get_deal_stats()
    scheduler = get_scheduler_status()
    cfg = _get_route_config()

    # Get last job run
    async with AsyncSessionLocal() as session:
        last_job_result = await session.execute(
            select(JobRun).order_by(JobRun.started_at.desc()).limit(1)
        )
        last_job = last_job_result.scalar_one_or_none()

    # Build route_deals from stats
    route_deals = []
    for route in stats.get("top_routes", []):
        # Get the most recent deal for this route
        async with AsyncSessionLocal() as session:
            recent_result = await session.execute(
                select(FlightDeal)
                .where(
                    FlightDeal.origin == route["origin"],
                    FlightDeal.destination == route["destination"],
                )
                .order_by(FlightDeal.seen_at.desc())
                .limit(1)
            )
            recent = recent_result.scalar_one_or_none()

        if recent:
            route_deals.append({
                "origin": recent.origin,
                "destination": recent.destination,
                "current_price": recent.current_price_usd,
                "original_price": recent.original_price_usd,
                "price_drop": recent.price_drop_percent,
                "airline": recent.airline,
                "deal_type": recent.deal_type,
                "deal_count": route["count"],
                "last_checked": recent.seen_at.strftime("%Y-%m-%d %H:%M")
                if recent.seen_at else None,
                "trend": "down" if recent.price_drop_percent > 0 else "flat",
            })

    return render(
        request,
        "dashboard/index.html",
        active_page="dashboard",
        stats=stats,
        scheduler=scheduler,
        config=cfg,
        last_job=last_job,
        route_deals=route_deals,
    )


@router.get("/dashboard/deals", response_class=HTMLResponse)
async def dashboard_deals(
    request: Request,
    user: dict = Depends(require_login),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    deal_type: str | None = Query(None),
    origin: str | None = Query(None),
    destination: str | None = Query(None),
) -> HTMLResponse:
    """Deal table page."""
    deals = await _get_deals(
        limit=limit,
        offset=offset,
        deal_type=deal_type,
        origin=origin,
        destination=destination,
    )

    filters = {
        "deal_type": deal_type or "",
        "origin": origin or "",
        "destination": destination or "",
    }

    return render(
        request,
        "dashboard/deals.html",
        active_page="deals",
        deals=deals,
        filters=filters,
    )


@router.get("/dashboard/deals/partial", response_class=HTMLResponse)
async def dashboard_deals_partial(
    request: Request,
    user: dict = Depends(require_login),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    deal_type: str | None = Query(None),
    origin: str | None = Query(None),
    destination: str | None = Query(None),
) -> HTMLResponse:
    """HTMX partial for additional deal rows."""
    deals = await _get_deals(
        limit=limit,
        offset=offset,
        deal_type=deal_type,
        origin=origin,
        destination=destination,
    )

    rows = []
    for deal in deals["deals"]:
        row = render(
            request,
            "partials/deal_row.html",
            deal=deal,
        ).body.decode()
        rows.append(row)

    if not rows:
        return HTMLResponse(
            '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text-muted);">No deals match your filters.</td></tr>'
        )

    return HTMLResponse("".join(rows))


@router.get("/dashboard/routes", response_class=HTMLResponse)
async def dashboard_routes(
    request: Request,
    user: dict = Depends(require_login),
) -> HTMLResponse:
    """Route management page."""
    cfg = _get_route_config()

    return render(
        request,
        "dashboard/routes.html",
        active_page="routes",
        config=cfg,
        error=None,
    )


def _reload_config():
    """Reload the application configuration from YAML."""
    path = "config/app.yaml"
    from app.config import AppConfig  # noqa: PLC0415
    config.app = AppConfig.from_yaml(path)


@router.post("/dashboard/routes/add")
async def dashboard_routes_add(
    request: Request,
    user: dict = Depends(require_login),
    airport_code: str = Form(...),
) -> HTMLResponse:
    """Add a destination airport."""
    code = airport_code.strip().upper()

    if len(code) != 3 or not code.isalpha():
        cfg = _get_route_config()
        return render(
            request,
            "dashboard/routes.html",
            active_page="routes",
            config=cfg,
            error="Invalid airport code. Use 3 uppercase letters (e.g., CDG).",
        )

    if code not in config.app.destinations:
        yaml_path = "config/app.yaml"
        if os.path.exists(yaml_path):
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        if "app" not in data:
            data["app"] = {}
        if "destinations" not in data["app"]:
            data["app"]["destinations"] = list(config.app.destinations)

        data["app"]["destinations"].append(code)
        with open(yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        _reload_config()

    response = HTMLResponse(status_code=200)
    response.headers["HX-Redirect"] = "/dashboard/routes"
    return response


@router.post("/dashboard/routes/remove")
async def dashboard_routes_remove(
    request: Request,
    user: dict = Depends(require_login),
    index: int = Form(...),
) -> HTMLResponse:
    """Remove a destination airport by index."""
    if 0 <= index < len(config.app.destinations):
        yaml_path = "config/app.yaml"
        if os.path.exists(yaml_path):
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        if "app" in data and "destinations" in data["app"]:
            dests = data["app"]["destinations"]
            if 0 <= index < len(dests):
                del dests[index]
            data["app"]["destinations"] = dests
            with open(yaml_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False)

            _reload_config()

    response = HTMLResponse(status_code=200)
    response.headers["HX-Redirect"] = "/dashboard/routes"
    return response


@router.get("/dashboard/history", response_class=HTMLResponse)
async def dashboard_history(
    request: Request,
    user: dict = Depends(require_login),
) -> HTMLResponse:
    """Job run history page."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(JobRun).order_by(JobRun.started_at.desc()).limit(100)
        )
        jobs = result.scalars().all()

    job_list = [
        {
            "job_id": j.job_id,
            "started_at": j.started_at.strftime("%Y-%m-%d %H:%M:%S")
            if j.started_at else None,
            "duration_seconds": j.duration_seconds,
            "deals_detected": j.deals_detected,
            "alerts_sent": j.alerts_sent,
            "status": j.status,
            "error_message": j.error_message,
        }
        for j in jobs
    ]

    return render(
        request,
        "dashboard/history.html",
        active_page="history",
        jobs=job_list,
    )


@router.get("/dashboard/settings", response_class=HTMLResponse)
async def dashboard_settings(
    request: Request,
    user: dict = Depends(require_login),
) -> HTMLResponse:
    """Settings display page."""
    config_info = await _get_config_display()
    return render(
        request,
        "dashboard/settings.html",
        active_page="settings",
        config_info=config_info,
    )
