# Flight Deal Monitor 🛫💰

[ARCHITECTURE](ARCHITECTURE.html) | [DOCUMENTATION](docs.html)

**IMPORTANT: This README.md is the source of truth. When code changes affect features, thresholds, or configuration, update this file in the same commit.**

Automated flight deal monitoring and alerting system that searches for flash sales and mistake fares, sending real-time alerts via Telegram, email, Slack, and Discord. Includes a web UI dashboard for route management and deal browsing.

## QUICKSTART

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp config/.env.example .env   # then edit .env with your API keys

# Run the app
python -m app.main             # starts on http://localhost:8787

# Open the dashboard
open http://localhost:8787/dashboard

# Run tests
pytest tests/ -v

# Lint
ruff check app/ tests/

# Docker
docker-compose up -d           # starts containerized app
curl http://localhost:8787/health  # verify health
```

## Features ✨

- **Route Monitoring**: Continuous monitoring of flight prices from home airports to destinations
- **Deal Detection**: Three-tier detection — flash sales (≥50% drop), deep flash (≥65% drop), and mistake fares (≥70% off median)
- **Web UI Dashboard**: Jinja2 + HTMX dashboard with dark theme — overview, deals, routes, history, settings
- **User Authentication**: Login/register system with session cookies for dashboard access
- **Real-time Alerts**: Telegram, email (SMTP), Slack, and Discord notifications with booking links
- **Long Weekend Monitoring**: Optional Thu→Sun and Fri→Mon round-trip deal scanning up to 12 months out
- **24h Deduplication**: Prevents duplicate alerts for the same flight
- **Auto Cleanup**: Expired deals are automatically purged daily
- **Smart Scheduling**: Regular sweeps (30min) + priority mistake fare checks (15min) + long weekend sweeps + daily cleanup
- **Error Alerting**: Sweep failures are reported via all configured notifiers
- **Price History**: Median price calculations for accurate deal detection, with trend analysis API
- **Multi API Support**: fli library (FREE Google Flights, primary) + SearchAPI ($4/1K, fallback) + Duffel Air API (backup)
- **Price Caching**: 6-hour TTL cache reduces API costs by skipping stable price searches
- **Health Monitoring**: Built-in health endpoints for Docker/Kubernetes
- **PostgreSQL Ready**: Alembic migrations for production database upgrade
- **Docker Ready**: Multi-stage Docker build for easy deployment

## Tech Stack 🏗️

- **Backend**: Python 3.11+ / FastAPI / APScheduler
- **Database**: SQLite (PostgreSQL upgrade path via Alembic)
- **ORM**: SQLModel (type-safe, SQLAlchemy-backed)
- **HTTP Client**: httpx (async)
- **APIs**: fli (free Google Flights, primary) + SearchAPI ($4/1K, fallback) + Duffel Air API (backup)
- **Notifications**: Telegram Bot API + SMTP email + Slack webhooks + Discord webhooks
- **Web UI**: Jinja2 templates + HTMX 1.9 + Alpine.js 3.13
- **Deployment**: Docker + docker-compose
- **Testing**: pytest + pytest-asyncio + pytest-mock

## Quick Start 🚀

### Prerequisites

- Python 3.11+
- [SearchAPI](https://www.searchapi.io/docs/google-flights-api) key (fallback, Google Flights)
- Duffel API credentials (backup, [get them here](https://duffel.com/docs/api))
- Telegram Bot token (create via [@BotFather](https://t.me/botfather))
- Docker (optional, for containerized deployment)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/bigknoxy/flight-deal-monitor.git
   cd flight-deal-monitor
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   ```bash
   cp config/.env.example .env
   # Edit .env with your API keys
   ```

4. **Run the application**:
   ```bash
   python -m app.main
   ```

The app will start on `http://localhost:8787`

### Docker Deployment

1. **Build and run with docker-compose**:
   ```bash
   docker-compose up -d
   ```

2. **View Logs**:
   ```bash
   docker-compose logs -f
   ```

3. **Check health status**:
   ```bash
   curl http://localhost:8787/health
   ```

## Web UI Dashboard 🖥️

The dashboard is available at `http://localhost:8787/dashboard` after registering an account.

### Pages

| Page | URL | Description |
|------|-----|-------------|
| **Login** | `/auth/login` | Sign in to your account |
| **Register** | `/auth/register` | Create a new account |
| **Dashboard** | `/dashboard` | Overview with stats, route cards, and scheduled jobs |
| **Deals** | `/dashboard/deals` | Browse and filter detected deals |
| **Routes** | `/dashboard/routes` | Add/remove destination airports, view long weekend config |
| **History** | `/dashboard/history` | Job run log with status, duration, deals, alerts |
| **Settings** | `/dashboard/settings` | Editable config form (notifiers, thresholds, sweep intervals, route multipliers, cache TTL, long-weekend toggle) — saves to DB |

### Dashboard Overview
- **Stats cards**: Total deals, active routes, scheduler status, last sweep time
- **Routes overview**: Per-route deal cards with price, trend, airline, deal type
- **Scheduled jobs table**: All jobs with next run time

### Deals Page
- Filter by deal type (mistake fare, flash sale, deep flash)
- Filter by origin/destination airport
- HTMX-powered "Load More" pagination button
- Columns: route, type, price, discount, airline, date, booking link

### Routes Page
- View home airports and configured destinations
- Add new destinations (validates 3-letter IATA codes)
- Remove destinations with Alpine.js animation
- Long weekend monitoring status display

### History Page
- Job run log with timestamps
- Status badges (success/failed/running)
- Duration, deals detected, alerts sent
- Error messages for failed runs

### Settings Page
- Editable form — changes persist to the database and take effect on reload (no restart needed)
- Sections: Application, Deal Thresholds, Sweep Intervals, Route Multipliers, Cache, Long Weekend, Environment

## Configuration ⚙️

### Environment Variables (.env)

```bash
# fli (primary - FREE Google Flights)
# No API key required - uses curl_cffi to access Google Flights directly

# SearchAPI (fallback - $4/1K)
SEARCHAPI_API_KEY=your_api_key

# Duffel API (backup)
DUFFEL_API_TOKEN=your_api_token

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
EMAIL_FROM=alerts@example.com
EMAIL_TO=you@example.com

# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Database
DATABASE_URL=sqlite:///./flight_deals.db

# PostgreSQL (optional, for production)
# DATABASE_URL=postgresql://user:pass@localhost:5432/flight_deals

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### App Configuration (config/app.yaml)

```yaml
app:
  home_airports:
    - "MCI"

  destinations:
    - "JFK"
    - "LGA"
    - "EWR"
    - "BOS"
    - "LHR"
    - "NRT"
    - "ICN"

  max_results_per_route: 10
  look_ahead_days: 90
  look_back_days: 30

  min_price_usd: 100
  max_alerts_per_hour: 10

  regular_sweep_interval: 1800  # 30 minutes
  mistake_sweep_interval: 900   # 15 minutes
  job_coalesce: true

  cache_ttl_minutes: 360        # 6 hours

  # Long weekend monitoring (optional)
  long_weekend:
    enabled: false
    interval_minutes: 60
    look_ahead_months: 12

  # Flexible dates (optional)
  flexible_dates:
    enabled: false
    range_days: 3

  # Multi-city routes (optional)
  multi_city:
    enabled: false
    max_stops: 2
```

#### Deal Thresholds

```yaml
app:
  deal_thresholds:
    mistake_fare_percent: 0.70   # ≥70% below median = mistake fare
    flash_sale_percent: 0.50     # ≥50% below median = flash sale
    deep_flash_percent: 0.65     # ≥65% below median = deep discount

  # Route-specific multipliers (adjust median price by route volatility)
  route_multipliers:
    domestic: 1.0         # Standard domestic routes
    transatlantic: 0.8    # More volatile, lower threshold
    transpacific: 0.7     # Most volatile, lowest threshold
    latin_america: 1.2    # Less volatile, higher threshold
    europe: 0.85          # Moderately volatile
```

## API Endpoints 📡

### GET `/`
Root endpoint with app info.

**Response**:
```json
{
  "name": "flight-deal-monitor",
  "version": "1.0.0",
  "description": "Automated flight deal monitoring and alerting system"
}
```

### GET `/health`
Health check endpoint. Returns scheduler status and job information.

**Response**:
```json
{
  "status": "healthy",
  "scheduler_running": true,
  "jobs": [
    {
      "id": "regular_sweep",
      "name": "Regular Flight Price Sweep",
      "next_run": "2024-06-01T12:30:00"
    }
  ],
  "job_count": 3
}
```

### GET `/config`
Get current configuration (without secrets). Returns all app settings including deal thresholds and route multipliers.

### GET `/deals`
List detected flight deals with pagination and filtering.

**Query Parameters**:
- `limit` (int, default 20) — results per page
- `offset` (int, default 0) — pagination offset
- `deal_type` (str, optional) — filter by type: `flash_sale`, `deep_flash`, `mistake_fare`
- `origin` (str, optional) — filter by origin airport code
- `destination` (str, optional) — filter by destination airport code

**Response**:
```json
{
  "total": 42,
  "limit": 20,
  "offset": 0,
  "deals": [
    {
      "id": 1,
      "origin": "MCI",
      "destination": "LHR",
      "deal_type": "mistake_fare",
      "price": 150.00,
      "median_price": 500.00,
      "url": "https://www.kayak.com/flights/MCI-LHR/2024-06-01",
      "seen_at": "2024-06-01T12:00:00",
      "expired_at": "2024-06-02T12:00:00"
    }
  ]
}
```

### GET `/deals/stats`
Get deal summary statistics.

**Response**:
```json
{
  "total_deals": 42,
  "by_type": {
    "flash_sale": 30,
    "deep_flash": 8,
    "mistake_fare": 4
  },
  "top_routes": [
    {"route": "MCI→LHR", "count": 12},
    {"route": "MCI→JFK", "count": 8}
  ]
}
```

### GET `/deals/{deal_id}`
Get a single deal by its ID.

**Response**: Full deal object (same fields as list response).

**Error**: Returns `404` if deal not found.

### GET `/deals/history`
Get price history and trend for a route.

**Query Parameters**:
- `origin` (str, required) — origin airport code
- `destination` (str, required) — destination airport code
- `days` (int, optional, default 90) — lookback window

**Response**:
```json
{
  "route": "MCI→LHR",
  "days": 90,
  "trend": "down",
  "history": [
    {"date": "2024-06-01", "median_price": 500.0, "lowest_price": 450.0, "count": 3},
    {"date": "2024-06-02", "median_price": 480.0, "lowest_price": 420.0, "count": 5}
  ]
}
```

## Development 👨‍💻

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/test_price_analysis.py -v
```

### Code Quality

```bash
# Lint with ruff
ruff check app/ tests/

# Type check with mypy
mypy app/ --ignore-missing-imports

# Format with black
black app/ tests/
```

### Project Structure

```
flight-deal-monitor/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Configuration management
│   ├── database.py          # Database setup (SQLite + PostgreSQL)
│   ├── auth.py              # Session management + require_login dependency
│   ├── cache.py             # TTL price caching
│   ├── scheduler.py         # APScheduler setup
│   ├── scheduler_jobs.py    # Job implementations (regular, mistake, long weekend, cleanup)
│   ├── alert.py             # Telegram bot
│   ├── models/
│   │   ├── flight.py        # Flight deal models
│   │   ├── job.py           # Job run models
│   │   └── user.py          # User model (auth)
│   ├── api/
│   │   ├── amadeus.py       # Amadeus client
│   │   ├── duffel.py        # Duffel client
│   │   └── searchapi.py     # SearchAPI client
│   ├── scrapers/
│   │   └── fli_client.py    # fli library wrapper
│   ├── notifiers/
│   │   ├── __init__.py
│   │   ├── base.py          # BaseNotifier ABC + rate limiting
│   │   ├── email.py         # EmailNotifier (SMTP via aiosmtplib)
│   │   ├── slack.py         # SlackNotifier (block kit payloads)
│   │   └── discord.py       # DiscordNotifier (color-coded embeds)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── dashboard.py     # Dashboard UI routes (9 endpoints)
│   │   └── auth.py          # Auth routes (login, register, logout)
│   ├── templates/
│   │   ├── __init__.py      # Jinja2Templates setup + render() helper
│   │   ├── base.html        # Main layout with sidebar nav
│   │   ├── dashboard/
│   │   │   ├── index.html   # Overview with stats + route cards
│   │   │   ├── deals.html   # Deal table with HTMX filters
│   │   │   ├── routes.html  # Route management with add/remove
│   │   │   ├── history.html # Job run log
│   │   │   └── settings.html # Editable config form (saves to DB)
│   │   ├── auth/
│   │   │   ├── auth_form.html  # Shared auth form template
│   │   │   ├── login.html      # Login page
│   │   │   └── register.html   # Register page
│   │   └── partials/
│   │       ├── deal_row.html    # Single deal table row
│   │       ├── deal_table.html  # Deal table with pagination
│   │       └── route_card.html  # Route card component
│   ├── static/
│   │   ├── css/
│   │   │   └── dashboard.css # Full dark theme stylesheet
│   │   └── js/
│   │       └── dashboard.js  # Sidebar toggle, toast dismiss, HTMX reinit
│   └── utils/
│       ├── price_analysis.py    # Deal detection + price history + trends
│       ├── deduplication.py     # 24h dedup
│       ├── long_weekend.py      # Long weekend date pair generation
│       ├── flexible_dates.py    # Date range expansion + multi-city routes
│       └── database_url.py      # Async database URL conversion
├── alembic/
│   ├── env.py               # Async Alembic environment
│   ├── script.py.mako       # Migration template
│   └── versions/            # Migration revisions
├── alembic.ini              # Alembic configuration
├── tests/
│   ├── conftest.py          # Shared fixtures (make_deal)
│   ├── test_alert.py
│   ├── test_alembic.py      # Migration tests (opt-in)
│   ├── test_api_clients.py
│   ├── test_auth.py         # Auth routes + session tests
│   ├── test_config.py
│   ├── test_dashboard.py    # Dashboard UI tests
│   ├── test_database_url.py # Database URL parsing tests
│   ├── test_deduplication.py
│   ├── test_email_notifier.py
│   ├── test_flexible_dates.py
│   ├── test_fli_integration.py  # opt-in: FLI_INTEGRATION_TEST=1
│   ├── test_long_weekend.py
│   ├── test_main.py
│   ├── test_price_analysis.py
│   ├── test_price_analysis_extended.py
│   ├── test_price_history.py
│   ├── test_scheduler.py
│   ├── test_scheduler_jobs.py
│   ├── test_scheduler_jobs_extended.py
│   ├── test_searchapi.py
│   ├── test_sweeps.py
│   └── test_webhook_notifiers.py
├── config/
│   ├── app.yaml
│   └── .env.example
├── docs/
│   └── FEATURES.md          # Detailed roadmap with eval suites
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── ARCHITECTURE.html
├── docs.html
└── README.md
```

## Deal Detection Logic 🎯

### Mistake Fares
- Triggered when price is ≥70% below median
- Example: Median $500, current $150 = 70% off → 🚨 URGENT!

### Deep Flash Sales
- Triggered when price is ≥65% below median
- Example: Median $500, current $175 = 65% off → ⚡ Deep Flash!

### Flash Sales
- Triggered when price is ≥50% below median
- Example: Median $500, current $250 = 50% off → 🔥 Alert!

### Route Multipliers
Route-specific multipliers adjust the effective median price before deal detection, accounting for route volatility:
- **Domestic** (1.0×): Standard threshold
- **Transatlantic** (0.8×): More volatile, lower bar for deals
- **Transpacific** (0.7×): Most volatile, lowest bar
- **Latin America** (1.2×): Less volatile, higher bar
- **Europe** (0.85×): Moderately volatile

Example: A transatlantic route with median $500 uses effective median $400 (500 × 0.8), making a $280 fare qualify as a flash sale (50% off $400) even though it's only 44% off the raw median.

### Price History
- Median calculated from last 30 days of pricing data
- More accurate than average (resistant to outliers)
- Cached for 6 hours to reduce API calls

## Notifications 📬

### Telegram
Alerts include flight route, departure date, airline, original vs current price, discount percentage, deal type, and booking link. Error alerts for sweep failures are sent to the same chat.

### Email (SMTP)
HTML-formatted email alerts with the same deal information. Configured via `SMTP_*` environment variables. Supports any SMTP server (Gmail, SendGrid, Mailgun, etc.).

### Slack
Rich block kit messages with deal-type emoji header, route/airline details, price comparison, and a "Book Now" button. Configured via `SLACK_WEBHOOK_URL`.

### Discord
Color-coded embeds (green for flash sales, orange for deep flash, red for mistake fares) with all deal details. Configured via `DISCORD_WEBHOOK_URL`.

### Long Weekend Monitoring
When enabled, the system scans for Thu→Sun and Fri→Mon round-trip deals. These are flagged with a "long_weekend" suffix in the route ID and sent through all configured notifiers.

## PostgreSQL Migration

To switch from SQLite to PostgreSQL:

1. Install PostgreSQL and create a database
2. Set `DATABASE_URL=postgresql://user:pass@localhost:5432/flight_deals` in `.env`
3. Run migrations:
   ```bash
   alembic upgrade head
   ```
4. Restart the app

The app automatically detects the database scheme and uses the appropriate async driver (`aiosqlite` for SQLite, `asyncpg` for PostgreSQL).

## Deployment Options 🌐

### Local Development
```bash
python -m app.main
```

### Docker Compose (Recommended)
```bash
docker-compose up -d
```

### Kubernetes
Create a deployment manifest using the Docker image:
```yaml
image: ghcr.io/bigknoxy/flight-deal-monitor:latest
```

### Cloud Services
- AWS ECS / EKS
- Google Cloud Run / GKE
- Azure Container Instances / AKS

## Monitoring 📊

### Health Checks
```bash
# Check app health
curl http://localhost:8787/health

# Check logs
docker-compose logs -f app
```

### Metrics to Track
- API calls per provider
- Alerts sent per day
- Deal detection accuracy
- Scheduler job success rate
- Database size

## Troubleshooting 🔧

### Common Issues

**Issue**: Telegram bot not sending alerts
- **Solution**: Check bot token and chat ID in `.env`
- **Solution**: Verify bot is added to the group/channel (if using group chat)

**Issue**: fli search failing
- **Solution**: Google blocks repeated requests; system will automatically use SearchAPI fallback
- **Solution**: Consider using SearchAPI for reliable results

**Issue**: Database locked errors
- **Solution**: Ensure only one app instance is running
- **Solution**: For production, consider PostgreSQL

**Issue**: No alerts being sent
- **Solution**: Check health endpoint: `/health`
- **Solution**: Verify deal thresholds in `config/app.yaml`
- **Solution**: Check logs: `docker-compose logs app`

**Issue**: Dashboard shows "Not Found"
- **Solution**: Ensure you're registered and logged in
- **Solution**: Check that the app is running on port 8787

## Architecture

For detailed architecture documentation, see [ARCHITECTURE.html](ARCHITECTURE.html).

## Documentation

For full documentation, see [docs.html](docs.html).

## Roadmap 🗺️

See [FEATURES.md](docs/FEATURES.md) for detailed specs, implementation plans,
test strategies, and eval suites for each feature.

### Priority Order

1. **Web UI Dashboard** ✅ — Jinja2 + HTMX dashboard for route management, deal
   browsing, sweep history, and config display. No build step, mobile-first.
2. **Email Alerts** ✅ — Parallel notification channel via SMTP. Same
   deal alert format, adapted for email.
3. **Price History API + Trends** ✅ — Daily median prices per route, trend
   detection, dashboard charts.
4. **Slack/Discord Webhooks** ✅ — Webhook-based notifiers using existing httpx
   dependency.
5. **PostgreSQL Support** ✅ — Alembic migrations, asyncpg driver, config-driven
   swap from SQLite.
6. **Multi-City / Flexible Dates** ✅ — Extend long weekend pattern to multi-stop
   itineraries and ±3 day date ranges.
7. **User Auth + Personalization** ✅ — Multi-user support with per-user routes
   and notification preferences.

### Eval Suite

Each feature includes snapshot-based eval tests using `syrupy` for regression
detection, plus performance benchmarks using `pytest-benchmark`. The eval suite
enables a GEPA (Generate → Evaluate → Propose → Adapt) self-improvement loop
that catches regressions before they ship.

## Contributing 🤝

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/amazing-feature`
3. Commit changes: `git commit -m 'feat: add amazing feature'`
4. Push to branch: `git push origin feat/amazing-feature`
5. Open a Pull Request

## License 📄

MIT License - see LICENSE file for details

## Acknowledgments 🙏

- fli library for free Google Flights access
- SearchAPI for reliable Google Flights API
- Duffel for their air booking API
- Telegram for their bot platform

---

**Built with ❤️ for travel hackers and deal hunters**
