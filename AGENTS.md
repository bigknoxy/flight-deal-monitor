# Flight Deal Monitor — Agent Guide

## Quick Start
```bash
pip install -r requirements.txt
cp config/.env.example .env  # edit with API keys
python -m app.main          # http://localhost:8787
```

## Commands
- **Dev server**: `python -m app.main` (port 8787, auto-reload)
- **Tests**: `pytest tests/ -v`
- **Single test**: `pytest tests/test_foo.py::test_bar -v`
- **Coverage**: `pytest tests/ --cov=app --cov-report=term-missing`
- **Lint**: `ruff check app/ tests/`
- **Typecheck**: `mypy app/ --ignore-missing-imports` (continue-on-error in CI)
- **Format**: `black app/ tests/`
- **CI order**: lint → typecheck → test → build (Docker push on main push only)
- **Docker**: `docker-compose up -d` (port 8787, health at `/health`)

## Architecture
- **FastAPI** app with Jinja2 + HTMX dashboard (no React/Vue)
- **APScheduler** with SQLAlchemyJobStore + AsyncIOExecutor for background sweeps
- **SQLite** default; PostgreSQL opt-in via `DATABASE_URL` + Alembic migrations
- **Auth**: itsdangerous signed cookies (7-day expiry), bcrypt passwords
- **Config layering**: `config/app.yaml` (routes, thresholds) + `.env` (secrets) → Pydantic `AppConfig`
- **Alert fallback chain**: fli (sync, free, primary) → SearchAPI (paid, fallback) → Duffel (backup)

### Model boundaries (easy to mix up)
- `app/models/flight.py` — domain only: `FlightDeal`, `AlertHistory`, `Airport`
- `app/models/job.py` — scheduler only: `ScheduledJob`, `JobRun`
- `app/models/route.py` — `MonitorRoute`, `RouteType`

### Key functions
| File | Function pattern |
|---|---|
| `app/scheduler_jobs.py` | `_scan_route()` sync wrapper (fli) → `_send_deal_alert()` notifier fan-out |
| `app/scrapers/fli_client.py` | Synchronous; invoked via `asyncio.get_event_loop().run_in_executor()` |
| `app/utils/price_analysis.py` | `detect_deal()`, `get_route_type()` |
| `app/utils/deduplication.py` | `is_flight_seen_recently()` — routes keyed on `generate_route_id()` hash |
| `app/cache.py` | TTL price cache (default 360 min) |
| `app/templates/__init__.py` | `render()` injects `config_version` into every template context |
| `app/main.py` | `/` → 307 `/dashboard`; dashboard routes require `require_login`; API routes (`/deals/*`, `/config`) do not |

## Testing
- `pytest-asyncio` with `asyncio_mode = "auto"` (configured in `pyproject.toml`)
- `pytest-mock` for all external calls — no real HTTP in unit tests
- `responses` library mocks HTTP for `fli_client` / `SearchAPI` client tests
- Integration tests: `FLI_INTEGRATION_TEST=1 pytest tests/test_fli_integration.py` (skipped by default)
- Alembic tests: opt-in, skipped by default
- Coverage target: 85% (hard gate via `pyproject.toml`)

## Config
- **Home airport**: MCI (hardcoded single origin)
- **19 destinations** in `config/app.yaml`
- **Deal thresholds**: 70% mistake, 65% deep flash, 50% flash sale
- **Route multipliers**: domestic 1.0, transatlantic 0.8, transpacific 0.7, latin_america 1.2, europe 0.85
- **Sweep intervals**: regular 1800s, mistake 900s, cleanup 24h
- **Long weekend**: opt-in (disabled by default), Thu→Sun + Fri→Mon pairs
- **Rate limit**: 10 alerts/hour across all notifiers

## Known Gotchas
- **`fli` is synchronous** — runs via `run_in_executor()` in `_scan_route()`
- **`flights` package** on PyPI (installed name), not `fli` — see `requirements.txt`
- **Scheduler SQLite job store** — `database_url` from `.env`; bare `sqlite://` will fail, needs trailing slash
- **`_start_job_run` / `_complete` / `_fail`** each open their own DB session (not the caller's)
- **`generate_route_id()`** includes `airline` + optional `suffix` in the hash; changing either invalidates the dedup key
- **`detect_deal()`** applies route multiplier only when `origin` and `destination` are provided
- **Telegram `send_alert()`** returns `str | None` (message_id); WebhookNotifier returns `str | None` (not bool)
- **`_send_deal_alert()`** uses `asyncio.gather(return_exceptions=True)` — individual notifier failures don't abort the sweep
- **`_reload_config()`** re-reads YAML and replaces `config.app` in-place; no restart needed
- Dashboard HTML lives in `app/templates/auth/`, `base.html`, `dashboard/`
- `ruff` ignores `E501`; `black` line length is 100
- `pyproject.toml` has Poetry config but `requirements.txt` is the CI source of truth
