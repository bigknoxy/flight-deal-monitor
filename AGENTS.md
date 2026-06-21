# Flight Deal Monitor — Agent Guide

## Quick Start
```bash
pip install -r requirements.txt
cp config/.env.example .env   # edit with API keys
python -m app.main             # starts on http://localhost:8000
```

## Commands
- **Run app**: `python -m app.main` (port 8000, 0.0.0.0)
- **Run tests**: `pytest tests/ -v`
- **Single test**: `pytest tests/test_foo.py::test_bar -v`
- **Coverage**: `pytest tests/ --cov=app --cov-report=term-missing`
- **Lint**: `ruff check app/ tests/`
- **Typecheck**: `mypy app/ --ignore-missing-imports` (continue-on-error in CI)
- **Format**: `black app/ tests/`
- **Docker**: `docker-compose up -d` (port 8000, health at `/health`)
- **CI order**: lint → test → build (Docker push on main push)

## Architecture
- **FastAPI** app with Jinja2+HTMX dashboard (no React/Vue)
- **APScheduler** with SQLAlchemyJobStore + AsyncIOExecutor for background sweeps
- **SQLite** default, PostgreSQL opt-in via `DATABASE_URL` + Alembic migrations
- **Auth**: itsdangerous signed cookies (7-day expiry), bcrypt passwords
- **API clients** (fallback chain): fli (free) → SearchAPI ($4/1K) → Duffel (backup)
- **Notifiers**: Telegram (primary), email (SMTP), Slack/Discord (webhooks)
- **Config**: `config/app.yaml` (routes, thresholds) + `.env` (secrets)

## Key Files
| File | Purpose |
|------|---------|
| `app/main.py` | Entrypoint, lifespan, API endpoints |
| `app/scheduler_jobs.py` | Sweep logic (`_scan_route`, `_send_deal_alert`) |
| `app/scheduler.py` | APScheduler setup (4 jobs: regular, mistake, cleanup, long_weekend) |
| `app/scrapers/fli_client.py` | fli library wrapper (synchronous, runs in executor) |
| `app/alert.py` | TelegramBot (rate-limited, MarkdownV2) |
| `app/notifiers/` | BaseNotifier ABC + email/slack/discord |
| `app/utils/price_analysis.py` | `detect_deal()`, `calculate_median_price()`, `get_route_type()` |
| `app/utils/deduplication.py` | 24h dedup via `is_flight_seen_recently()` |
| `app/cache.py` | TTL price cache (6h default) |
| `app/config.py` | Pydantic config from YAML + env |
| `app/database.py` | AsyncSessionLocal factory |
| `app/auth.py` | `require_login()` FastAPI dependency |
| `app/routes/dashboard.py` | 9 dashboard endpoints |
| `app/routes/auth.py` | Login/register/logout |
| `app/templates/__init__.py` | `render()` helper injecting `config_version` |
| `tests/conftest.py` | `make_deal` fixture |

## Config
- **Home airport**: MCI (single)
- **19 destinations** in `config/app.yaml`
- **Deal thresholds**: 70% mistake, 65% deep flash, 50% flash sale
- **Route multipliers**: domestic 1.0, transatlantic 0.8, transpacific 0.7, latin_america 1.2, europe 0.85
- **Sweep intervals**: regular 1800s, mistake 900s, cleanup 24h
- **Long weekend**: opt-in (disabled by default), Thu→Sun + Fri→Mon pairs
- **Cache TTL**: 360 min (6h)
- **Rate limit**: 10 alerts/hour across all notifiers

## Testing
- `pytest-asyncio` with `asyncio_mode = "auto"`
- `pytest-mock` for mocking API clients and notifiers
- `make_deal` fixture in `conftest.py` for creating FlightDeal instances
- Integration tests: `FLI_INTEGRATION_TEST=1 pytest tests/test_fli_integration.py`
- Alembic tests: opt-in, 1 skipped by default
- Coverage target: 85% (enforced in CI)

## Known Gotchas
- **fli is synchronous** — runs via `run_in_executor()` in `_scan_route()`
- **fli `_to_dict()`** converts fli results to SearchAPI-compatible dict format
- **fli round trips disabled** — Google returns None for multi-leg; one-way only
- **`flights` package** on PyPI (not `fli`) — pinned in requirements.txt
- **httpx/pydantic pins relaxed** to `>=` to resolve `flights` dependency conflicts
- **Scheduler uses SQLite job store** — URL is `config.env.database_url` with `sqlite://` → `sqlite:///` fix
- **`_start_job_run` opens its own session** (not the caller's) — same for `_complete`/`_fail`
- **`is_flight_seen_recently`** checks `route_id` hash, not raw route params
- **`generate_route_id`** includes `airline` + optional `suffix` in hash
- **`detect_deal`** applies route multiplier when origin/destination provided
- **`get_route_type`** uses hardcoded airport sets (US, EU, Asia, LATAM)
- **Telegram `send_alert`** returns `str | None` (message_id or None)
- **WebhookNotifier `send_alert`** returns `str | None` (not bool)
- **`_send_deal_alert`** uses `asyncio.gather` with `return_exceptions=True`
- **Root `/`** redirects to `/dashboard` (307)
- **Dashboard routes** require login via `require_login` dependency
- **`_reload_config()`** re-reads YAML and replaces `config.app` in-place
- **Dockerfile** uses multi-stage build, port 8000, HEALTHCHECK
- **CI** runs on push/PR to main/develop; Docker push on main push only
- **GitHub Pages** deploys repo root via `peaceiris/actions-gh-pages@v3`
- **`.nojekyll`** file exists — preserve it
- **`bcrypt<4.2`** pin in requirements.txt for passlib compatibility
- **`jinja2`** explicitly in requirements.txt (not a transitive dep)
- **`alembic/script.py.mako`** and `alembic/versions/` excluded from ruff
- **mypy errors** on SQLAlchemy typing (arg-type, call-overload) — not blocking CI
- **`ruff`** select: E, F, I, N, W, UP; ignore E501 (line length)
- **`black`** line length: 100
- **`pyproject.toml`** has Poetry config but `requirements.txt` is the source of truth for CI
- **App runs on port 8002** in production (ufw open, 0.0.0.0 binding) — Docker uses 8000
