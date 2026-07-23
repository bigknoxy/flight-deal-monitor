"""Dashboard routes for the web UI."""

import asyncio
import logging
import os
from datetime import datetime, timedelta

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

logger = logging.getLogger(__name__)

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
    """Get flight deals grouped by route+date+airline, showing cheapest per group."""
    async with AsyncSessionLocal() as session:
        query = select(
            FlightDeal.origin,
            FlightDeal.destination,
            FlightDeal.departure_date,
            FlightDeal.airline,
            func.min(FlightDeal.current_price_usd).label("cheapest_price"),
            func.min(FlightDeal.original_price_usd).label("original_price"),
            func.min(FlightDeal.price_drop_percent).label("max_drop"),
            func.min(FlightDeal.id).label("first_id"),
            func.min(FlightDeal.booking_url).label("booking_url"),
            func.min(FlightDeal.seen_at).label("seen_at"),
            func.min(FlightDeal.deal_type).label("deal_type"),
            func.min(FlightDeal.flight_numbers).label("flight_numbers"),
            func.count().label("option_count"),
        ).where(FlightDeal.expired_at > datetime.utcnow())

        if deal_type:
            query = query.where(FlightDeal.deal_type == deal_type)
        if origin:
            query = query.where(FlightDeal.origin == origin.upper())
        if destination:
            query = query.where(FlightDeal.destination == destination.upper())

        query = query.group_by(
            FlightDeal.origin,
            FlightDeal.destination,
            FlightDeal.departure_date,
            FlightDeal.airline,
        ).order_by(func.min(FlightDeal.seen_at).desc())

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total_count = total_result.scalar() or 0

        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        rows = result.all()

        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "deals": [
                {
                    "id": r.first_id,
                    "route_id": f"{r.origin}-{r.destination}-{r.departure_date}-{r.airline}",
                    "origin": r.origin,
                    "destination": r.destination,
                    "departure_date": r.departure_date,
                    "airline": r.airline,
                    "flight_numbers": r.flight_numbers,
                    "original_price_usd": r.original_price,
                    "current_price_usd": r.cheapest_price,
                    "price_drop_percent": r.max_drop,
                    "deal_type": r.deal_type,
                    "booking_url": r.booking_url,
                    "seen_at": r.seen_at.isoformat() if r.seen_at else None,
                    "option_count": r.option_count,
                }
                for r in rows
            ],
        }


async def _get_deal_stats() -> dict:
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


async def _get_config_display() -> dict:
    """Get config for display (secrets masked)."""

    # Mask any value that is set; never reveal raw tokens/passwords in the UI.
    def _mask(value: str) -> str:
        return "****" if value else ""

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
            "telegram_bot_token": _mask(config.env.telegram_bot_token),
            "telegram_chat_id": _mask(config.env.telegram_chat_id),
            "smtp_host": config.env.smtp_host,
            "smtp_port": config.env.smtp_port,
            "smtp_user": _mask(config.env.smtp_user),
            "smtp_pass": _mask(config.env.smtp_pass),
            "email_from": config.env.email_from,
            "email_to": config.env.email_to,
            "slack_webhook_url": _mask(config.env.slack_webhook_url),
            "discord_webhook_url": _mask(config.env.discord_webhook_url),
            "searchapi_api_key": _mask(config.env.searchapi_api_key),
            "amadeus_client_id": _mask(config.env.amadeus_client_id),
            "amadeus_client_secret": _mask(config.env.amadeus_client_secret),
            "duffel_api_token": _mask(config.env.duffel_api_token),
            "amadeus_env": config.env.amadeus_env,
            "log_level": config.env.log_level,
        },
    }


async def _get_detection_status() -> dict:
    """Aggregate detection-health signals for the dashboard banner.

    Surfaces:
      - last_success_at: most recent JobRun with status='success' (completed_at
        when present, else started_at). None if no successful runs exist.
      - last_success_age_hours: hours since last_success_at (None if never).
      - routes_with_zero_deals: list of "ORIG-DEST" configured routes that have
        produced zero FlightDeal rows whose seen_at is within STALE_ROUTE_DAYS.
      - is_stale: True when no successful scan in STALE_SCAN_HOURS, OR any
        configured route has zero recent deals.
    """
    stale_scan_hours = 6
    stale_route_days = 7

    async with AsyncSessionLocal() as session:
        last_success_result = await session.execute(
            select(JobRun)
            .where(JobRun.status == "success")
            .order_by(JobRun.completed_at.desc(), JobRun.started_at.desc())
            .limit(1)
        )
        last_success = last_success_result.scalar_one_or_none()

    last_success_at: datetime | None = None
    last_success_age_hours: float | None = None
    if last_success:
        last_success_at = last_success.completed_at or last_success.started_at
        last_success_age_hours = round(
            (datetime.utcnow() - last_success_at).total_seconds() / 3600.0, 1
        )

    home_airports = config.app.home_airports
    destinations = config.app.destinations
    stale_since = datetime.utcnow() - timedelta(days=stale_route_days)

    routes_with_zero_deals: list[str] = []
    async with AsyncSessionLocal() as session:
        for origin in home_airports:
            for dest in destinations:
                count_result = await session.execute(
                    select(func.count())
                    .select_from(FlightDeal)
                    .where(
                        FlightDeal.origin == origin.upper(),
                        FlightDeal.destination == dest.upper(),
                        FlightDeal.seen_at >= stale_since,
                    )
                )
                if (count_result.scalar() or 0) == 0:
                    routes_with_zero_deals.append(f"{origin.upper()}-{dest.upper()}")

    is_stale = (
        last_success_age_hours is None
        or last_success_age_hours >= stale_scan_hours
        or len(routes_with_zero_deals) > 0
    )

    return {
        "last_success_at": last_success_at,
        "last_success_age_hours": last_success_age_hours,
        "routes_with_zero_deals": routes_with_zero_deals,
        "stale_scan_hours": stale_scan_hours,
        "stale_route_days": stale_route_days,
        "is_stale": is_stale,
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
    notifier_status = config.notifier_status()
    detection_status = await _get_detection_status()

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
            route_deals.append(
                {
                    "origin": recent.origin,
                    "destination": recent.destination,
                    "current_price": recent.current_price_usd,
                    "original_price": recent.original_price_usd,
                    "price_drop": recent.price_drop_percent,
                    "airline": recent.airline,
                    "deal_type": recent.deal_type,
                    "deal_count": route["count"],
                    "last_checked": recent.seen_at.strftime("%Y-%m-%d %H:%M")
                    if recent.seen_at
                    else None,
                    "trend": "down" if recent.price_drop_percent > 0 else "flat",
                }
            )

    return render(
        request,
        "dashboard/index.html",
        active_page="dashboard",
        stats=stats,
        scheduler=scheduler,
        config=cfg,
        last_job=last_job,
        route_deals=route_deals,
        notifier_status=notifier_status,
        detection_status=detection_status,
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
            '<tr><td colspan="9" style="text-align:center;padding:2rem;color:var(--text-muted);">No deals match your filters.</td></tr>'
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
            if j.started_at
            else None,
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
    saved: bool = False,
    save_error: str | None = None,
    test_result: dict | None = None,
) -> HTMLResponse:
    """Settings display page."""
    config_info = await _get_config_display()
    return render(
        request,
        "dashboard/settings.html",
        active_page="settings",
        app=config_info["app"],
        env=config_info["env"],
        saved=saved,
        save_error=save_error,
        test_result=test_result,
    )


@router.post("/dashboard/settings/test-alerts")
async def dashboard_settings_test_alerts(
    request: Request,
    user: dict = Depends(require_login),
) -> HTMLResponse:
    """Fire test_connection() on every notifier in parallel, render results.

    Returns a partial HTML block (id=\"test-alert-results\") suitable for
    HTMX out-of-band swap. Each notifier returns True/False; partial config
    or unconfigured channels show as \"not configured\" instead of \"failed\".
    """
    from app.alert import telegram_bot
    from app.notifiers.discord import discord_notifier
    from app.notifiers.email import email_notifier
    from app.notifiers.slack import slack_notifier

    status = config.notifier_status()

    tasks = [
        telegram_bot.test_connection(),
        email_notifier.test_connection(),
        slack_notifier.test_connection(),
        discord_notifier.test_connection(),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    channel_names = ["telegram", "email", "slack", "discord"]

    per_channel: dict[str, str] = {}
    any_ok = False
    for name, configured, result in zip(channel_names, [status["telegram"], status["email"], status["slack"], status["discord"]], results):
        if not configured:
            per_channel[name] = "not_configured"
            continue
        if isinstance(result, Exception):
            per_channel[name] = "error"
        elif result is True:
            per_channel[name] = "ok"
            any_ok = True
        else:
            per_channel[name] = "failed"

    return render(
        request,
        "dashboard/_test_alerts_results.html",
        active_page="settings",
        per_channel=per_channel,
        any_ok=any_ok,
    )


@router.post("/dashboard/settings/save")
async def dashboard_settings_save(
    request: Request,
    user: dict = Depends(require_login),
    telegram_bot_token: str = Form(""),
    telegram_chat_id: str = Form(""),
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_user: str = Form(""),
    smtp_pass: str = Form(""),
    email_from: str = Form(""),
    email_to: str = Form(""),
    slack_webhook_url: str = Form(""),
    discord_webhook_url: str = Form(""),
    home_airports: str = Form(""),
    mistake_fare_percent: int = Form(70),
    deep_flash_percent: int = Form(65),
    flash_sale_percent: int = Form(50),
    regular_sweep_interval: int = Form(1800),
    mistake_sweep_interval: int = Form(900),
    mult_domestic: float = Form(1.0),
    mult_transatlantic: float = Form(0.8),
    mult_transpacific: float = Form(0.7),
    mult_latin_america: float = Form(1.2),
    mult_europe: float = Form(0.85),
    cache_ttl_minutes: int = Form(360),
    max_results_per_route: int = Form(10),
    look_ahead_days: int = Form(90),
    min_price_usd: int = Form(100),
    max_alerts_per_hour: int = Form(10),
    long_weekend_enabled: str = Form("false"),
    long_weekend_interval: int = Form(60),
    long_weekend_look_ahead: int = Form(12),
    log_level: str = Form("INFO"),
    job_coalesce: str = Form("true"),
) -> HTMLResponse:
    """Save all settings to config/app.yaml and .env."""
    try:
        # --- Save app.yaml ---
        yaml_path = "config/app.yaml"
        if os.path.exists(yaml_path):
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        airports = [a.strip().upper() for a in home_airports.split(",") if a.strip()]

        data["app"] = {
            "home_airports": airports,
            "destinations": config.app.destinations,
            "deal_thresholds": {
                "mistake_fare_percent": mistake_fare_percent / 100.0,
                "deep_flash_percent": deep_flash_percent / 100.0,
                "flash_sale_percent": flash_sale_percent / 100.0,
            },
            "regular_sweep_interval": regular_sweep_interval,
            "mistake_sweep_interval": mistake_sweep_interval,
            "route_multipliers": {
                "domestic": mult_domestic,
                "transatlantic": mult_transatlantic,
                "transpacific": mult_transpacific,
                "latin_america": mult_latin_america,
                "europe": mult_europe,
            },
            "cache_ttl_minutes": cache_ttl_minutes,
            "max_results_per_route": max_results_per_route,
            "look_ahead_days": look_ahead_days,
            "look_back_days": config.app.look_back_days,
            "min_price_usd": min_price_usd,
            "max_alerts_per_hour": max_alerts_per_hour,
            "job_coalesce": job_coalesce == "true",
            "long_weekend": {
                "enabled": long_weekend_enabled == "true",
                "interval_minutes": long_weekend_interval,
                "look_ahead_months": long_weekend_look_ahead,
            },
            "flexible_dates": {
                "enabled": config.app.flexible_dates.enabled,
                "range_days": config.app.flexible_dates.range_days,
            },
            "multi_city": {
                "enabled": config.app.multi_city.enabled,
                "max_stops": config.app.multi_city.max_stops,
            },
        }

        with open(yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        _reload_config()

        # --- Save .env ---
        env_path = ".env"
        env_lines = []
        env_updates = {
            "TELEGRAM_BOT_TOKEN": telegram_bot_token,
            "TELEGRAM_CHAT_ID": telegram_chat_id,
            "SMTP_HOST": smtp_host,
            "SMTP_PORT": str(smtp_port),
            "SMTP_USER": smtp_user,
            "EMAIL_FROM": email_from,
            "EMAIL_TO": email_to,
            "SLACK_WEBHOOK_URL": slack_webhook_url,
            "DISCORD_WEBHOOK_URL": discord_webhook_url,
            "LOG_LEVEL": log_level.upper(),
        }
        if smtp_pass:
            env_updates["SMTP_PASS"] = smtp_pass

        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    stripped = line.strip()
                    if "=" in stripped and not stripped.startswith("#"):
                        key = stripped.split("=", 1)[0].strip()
                        if key in env_updates:
                            val = env_updates.pop(key)
                            if val:
                                env_lines.append(f"{key}={val}\n")
                            continue
                    env_lines.append(line)

        for key, val in env_updates.items():
            if val:
                env_lines.append(f"{key}={val}\n")

        with open(env_path, "w") as f:
            f.writelines(env_lines)

        # Reload env config
        from app.config import EnvConfig  # noqa: PLC0415

        config.env = EnvConfig()

        # Rebuild Telegram bot with new token
        from app.alert import telegram_bot  # noqa: PLC0415

        telegram_bot.bot_token = config.env.telegram_bot_token
        telegram_bot.chat_id = config.env.telegram_chat_id
        telegram_bot.base_url = f"https://api.telegram.org/bot{telegram_bot.bot_token}"

        return await dashboard_settings(request, user, saved=True, save_error=None)

    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return await dashboard_settings(request, user, saved=False, save_error=str(e))
