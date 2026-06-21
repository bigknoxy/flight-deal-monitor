# Flight Deal Monitor 🛫💰

[ARCHITECTURE](ARCHITECTURE.html) | [DOCUMENTATION](docs.html)

**IMPORTANT: This README.md is the source of truth. When code changes affect features, thresholds, or configuration, update this file in the same commit.**

Automated flight deal monitoring and alerting system that searches for flash sales and mistake fares, sending real-time alerts via Telegram.

## QUICKSTART

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp config/.env.example .env   # then edit .env with your API keys

# Run the app
python -m app.main             # starts on http://localhost:8000

# Run tests
pytest tests/ -v

# Lint
ruff check app/ tests/

# Docker
docker-compose up -d           # starts containerized app
curl http://localhost:8000/health  # verify health
```

## Features ✨

- **Route Monitoring**: Continuous monitoring of flight prices from home airports to destinations
- **Deal Detection**: Three-tier detection — flash sales (≥50% drop), deep flash (≥65% drop), and mistake fares (≥70% off median)
- **Real-time Alerts**: Instant Telegram notifications with booking links
- **24h Deduplication**: Prevents duplicate alerts for the same flight
- **Auto Cleanup**: Expired deals are automatically purged daily
- **Smart Scheduling**: Regular sweeps (30min) + priority mistake fare checks (15min) + daily cleanup
- **Error Alerting**: Sweep failures are reported via Telegram for immediate awareness
- **Price History**: Median price calculations for accurate deal detection
- **Multi API Support**: fli library (FREE Google Flights, primary) + SearchAPI ($4/1K, fallback) + Duffel Air API (backup)
- **Note**: fli uses curl_cffi to access Google Flights API — works intermittently as Google blocks repeated requests
- **Price Caching**: 6-hour TTL cache reduces API costs by skipping stable price searches
- **Health Monitoring**: Built-in health endpoints for Docker/Kubernetes
- **Docker Ready**: Multi-stage Docker build for easy deployment

## Tech Stack 🏗️

- **Backend**: Python 3.11+ / FastAPI / APScheduler
- **Database**: SQLite (PostgreSQL upgrade path available)
- **ORM**: SQLModel (type-safe, SQLAlchemy-backed)
- **HTTP Client**: httpx (async)
- **APIs**: fli (free Google Flights, primary) + SearchAPI ($4/1K, fallback) + Duffel Air API (backup)
- **Note**: fli works intermittently due to Google blocking; SearchAPI is the reliable fallback
- **Notifications**: Telegram Bot API
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

The app will start on `http://localhost:8000`

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
   curl http://localhost:8000/health
   ```

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

# Database
DATABASE_URL=sqlite:///./flight_deals.db

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
      "url": "https://www.google.com/travel/flights?...",
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
│   ├── database.py          # Database setup
│   ├── models/
│   │   ├── flight.py        # Flight deal models
│   │   └── job.py           # Job models
│   ├── api/
│   │   ├── amadeus.py       # Amadeus client
│   │   ├── duffel.py        # Duffel client
│   │   └── searchapi.py     # SearchAPI client
│   ├── scrapers/
│   │   └── fli_client.py    # fli library wrapper
│   ├── alert.py             # Telegram bot
│   ├── cache.py             # TTL price caching
│   ├── scheduler.py         # APScheduler setup
│   ├── scheduler_jobs.py    # Job implementations
│   └── utils/
│       ├── price_analysis.py   # Deal detection logic
│       └── deduplication.py    # 24h dedup
├── tests/
│   ├── test_alert.py
│   ├── test_api_clients.py
│   ├── test_config.py
│   ├── test_deduplication.py
│   ├── test_fli_integration.py  # opt-in: FLI_INTEGRATION_TEST=1
│   ├── test_main.py
│   ├── test_price_analysis.py
│   ├── test_price_analysis_extended.py
│   ├── test_scheduler.py
│   ├── test_scheduler_jobs.py
│   ├── test_scheduler_jobs_extended.py
│   ├── test_searchapi.py
│   └── test_sweeps.py
├── config/
│   ├── app.yaml
│   └── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
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

## Telegram Alerts 📱

Alerts include:
- Flight route (Origin → Destination)
- Departure date and airline
- Original price vs current price
- Percentage discount
- Deal type (flash sale, deep flash, or mistake fare)
- Direct booking link
- Expiration warning (24 hours)

**Example Alert**:
```
🔥 Flight Deal Alert

Flash Sale

📍 MCI → LHR
📅 2024-06-15
✈️ British Airways

💰 $500.00 → $300.00
📉 50.0% OFF

[Book Now](https://example.com/book)

Deal expires in 24 hours
```

**Error Alerts**: Sweep failures are automatically reported to the same Telegram chat with error details, ensuring silent failures are immediately visible.

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
curl http://localhost:8000/health

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

## Architecture

For detailed architecture documentation, see [ARCHITECTURE.html](ARCHITECTURE.html).

## Documentation

For full documentation, see [docs.html](docs.html).

## Roadmap 🗺️

See [FEATURES.md](docs/FEATURES.md) for detailed specs, implementation plans,
test strategies, and eval suites for each feature.

### Priority Order

1. **Web UI Dashboard** — Jinja2 + HTMX dashboard for route management, deal
   browsing, sweep history, and config display. No build step, mobile-first.
2. **Email Alerts** — Parallel notification channel via SMTP/SendGrid. Same
   deal alert format, adapted for email.
3. **Price History API + Trends** — Daily median prices per route, trend
   detection, dashboard charts.
4. **Slack/Discord Webhooks** — Webhook-based notifiers using existing httpx
   dependency. ~40 lines each.
5. **PostgreSQL Support** — Alembic migrations, asyncpg driver, config-driven
   swap from SQLite.
6. **Multi-City / Flexible Dates** — Extend long weekend pattern to multi-stop
   itineraries and ±3 day date ranges.
7. **User Auth + Personalization** — Multi-user support with per-user routes
   and notification preferences. Deferred until needed.

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