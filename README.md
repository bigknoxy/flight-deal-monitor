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
- **Deal Detection**: Identifies flash sales (≥50% drop) and mistake fares (≥70% off median)
- **Real-time Alerts**: Instant Telegram notifications with booking links
- **24h Deduplication**: Prevents duplicate alerts for the same flight
- **Smart Scheduling**: Regular sweeps (30min) + priority mistake fare checks (15min)
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
  cache_variance_threshold: 0.05
```

#### Deal Thresholds

```yaml
app:
  deal_thresholds:
    mistake_fare_percent: 0.70   # ≥70% below median = mistake fare
    flash_sale_percent: 0.50     # ≥50% below median = flash sale
    deep_flash_percent: 0.65     # ≥65% below median = deep discount
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
Health check endpoint.

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
  "job_count": 2
}
```

### GET `/config`
Get current configuration (without secrets).

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
│   ├── test_api_clients.py
│   ├── test_price_analysis.py
│   └── test_deduplication.py
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

### Flash Sales
- Triggered when price is ≥50% below median
- Example: Median $500, current $250 = 50% off → 🔥 Alert!

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
- Deal type (flash sale or mistake fare)
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

- [ ] Web UI for managing monitored routes
- [ ] Multi-city itinerary builder
- [ ] Points/miles integration and valuation
- [ ] PostgreSQL support for production
- [ ] Email alerts (in addition to Telegram)
- [ ] User authentication and personalized alerts
- [ ] Historical deal tracking and analytics

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