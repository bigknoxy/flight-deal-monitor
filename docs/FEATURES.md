# Flight Deal Monitor — Feature Roadmap

This document defines the planned feature roadmap, organized by priority and
dependency. Each feature includes a spec, implementation plan, test strategy,
and eval suite for GEPA-style self-improvement.

---

## Priority Matrix

| Feature | User Value | Effort | Risk | Dependencies |
|---------|-----------|--------|------|-------------|
| Web UI Dashboard | High | Medium | Low | Existing API |
| Email Alerts | High | Low | Low | None |
| PostgreSQL Support | Medium | Low | Medium | None |
| Price History API + Trends | Medium | Low | Low | None |
| Slack/Discord Webhooks | Medium | Very Low | Low | None |
| Multi-City / Flexible Dates | Medium | Medium | Low | Long Weekend |
| User Auth + Personalization | Low | High | High | Web UI |

---

## Phase 1: Web UI Dashboard

### Spec

A lightweight, server-rendered dashboard served from FastAPI using Jinja2 + HTMX.
No build step, no Node.js, no SPA framework. Mobile-first, dark theme matching
existing docs pages.

### Pages

1. **Dashboard** (`/dashboard`) — Overview of all routes with current lowest price,
   trend indicator (up/down/flat), last-checked timestamp, and deal count badge.
   Cards for each route, sorted by deal urgency.

2. **Deals** (`/dashboard/deals`) — Full deal table with sorting by price drop %,
   deal type, route, date. Inline filtering by type/origin/destination. Pagination
   via HTMX (scroll or "load more" button).

3. **Route Management** (`/dashboard/routes`) — Add/remove destinations via form.
   Current list shown as removable chips. Home airport config. Long weekend toggle.

4. **Sweep History** (`/dashboard/history`) — Job run log: timestamps, duration,
   deals found, alerts sent, status (success/failed). Failed runs highlighted.

5. **Settings** (`/dashboard/settings`) — Deal thresholds (sliders), sweep intervals,
   cache TTL. Read-only for now (editable via YAML), but shows current values.

### Implementation Plan

```
app/
  templates/
    base.html              # Layout: nav, sidebar, dark theme
    dashboard/
      index.html           # Route overview cards
      deals.html           # Deal table with HTMX pagination
      routes.html          # Route management form
      history.html         # Job run log
      settings.html        # Config display
    partials/
      deal_row.html        # Single deal row for HTMX swap
      route_card.html      # Single route card for HTMX swap
      pagination.html      # HTMX pagination controls
  routes/
    __init__.py
    dashboard.py           # Dashboard page routes
    partials.py            # HTMX fragment routes
  static/
    css/
      dashboard.css        # Dark theme styles
    js/
      dashboard.js         # HTMX init, Alpine.js behaviors
```

**New dependencies:** `jinja2`, `jinja2-fragments`, `python-multipart` (for forms),
`fastapi-htmx` (optional, can use raw HTMX headers).

**No new API endpoints needed** — the dashboard reads from existing endpoints
(`/deals`, `/deals/stats`, `/health`, `/config`). Route management writes to
`config/app.yaml` via a new `PUT /config/routes` endpoint.

### Test Strategy

| Test | Type | What it covers |
|------|------|---------------|
| `test_dashboard_routes.py` | Unit | Each dashboard page returns 200, renders correct template |
| `test_dashboard_deals_pagination.py` | Unit | HTMX pagination returns correct partials |
| `test_dashboard_route_management.py` | Unit | Add/remove route updates config, validates airport codes |
| `test_dashboard_partials.py` | Unit | Each partial renders with empty/null data without crashing |
| `test_dashboard_integration.py` | Integration | Full page render with mocked DB data |

### Eval Suite

```python
# tests/evals/test_dashboard_render.py
def test_dashboard_renders_with_no_deals(snapshot):
    """Dashboard should render gracefully with empty state."""
    response = client.get("/dashboard")
    assert snapshot == response.text  # Snapshot: empty state HTML

def test_dashboard_renders_with_deals(snapshot):
    """Dashboard should render deal cards correctly."""
    seed_deals(5)
    response = client.get("/dashboard")
    assert snapshot == response.text  # Snapshot: 5 deal cards

def test_dashboard_route_card_format(snapshot):
    """Route card should show price, trend, last-checked."""
    seed_route_data("MCI", "LHR", price=450, trend="down")
    response = client.get("/dashboard")
    assert snapshot == response.text  # Snapshot: route card format
```

---

## Phase 2: Email Alerts

### Spec

Parallel notification channel to Telegram. Users configure SMTP or SendGrid in `.env`.
Alerts sent to a configurable email address. Same deal alert format, adapted for email.

### Implementation Plan

```
app/
  notifiers/
    __init__.py
    email.py       # EmailNotifier class
    base.py        # Abstract base for notifiers
```

**`app/notifiers/base.py`:**
```python
from abc import ABC, abstractmethod
from app.models.flight import FlightDeal

class BaseNotifier(ABC):
    @abstractmethod
    async def send_alert(self, deal: FlightDeal) -> bool: ...
    @abstractmethod
    async def send_error_alert(self, message: str) -> bool: ...
    @abstractmethod
    async def test_connection(self) -> bool: ...
```

**`app/notifiers/email.py`:**
```python
class EmailNotifier(BaseNotifier):
    def __init__(self):
        self.smtp_host = config.env.smtp_host
        self.smtp_port = config.env.smtp_port
        self.smtp_user = config.env.smtp_user
        self.smtp_pass = config.env.smtp_pass
        self.from_addr = config.env.email_from
        self.to_addr = config.env.email_to

    async def send_alert(self, deal: FlightDeal) -> bool:
        html = self._render_deal_html(deal)
        subject = f"Flight Deal: {deal.origin}→{deal.destination} ${deal.current_price_usd:.0f}"
        return await self._send_email(subject, html)

    def _render_deal_html(self, deal: FlightDeal) -> str:
        # Jinja2 template for deal email
        ...
```

**Config additions (`.env`):**
```
# Email (optional, for email alerts)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
EMAIL_FROM=alerts@yourdomain.com
EMAIL_TO=you@example.com
```

**Integration into alert pipeline:** The `_send_deal_alert()` function in
`scheduler_jobs.py` calls both `telegram_bot.send_alert()` and
`email_notifier.send_alert()` in parallel. If one fails, the other still succeeds.

### Test Strategy

| Test | Type | What it covers |
|------|------|---------------|
| `test_email_notifier.py` | Unit | HTML rendering, subject line, rate limiting |
| `test_email_smtp_mock.py` | Unit | SMTP send with mocked `aiosmtplib` |
| `test_email_integration.py` | Integration | Full send with Mailtrap (opt-in) |
| `test_alert_pipeline_parallel.py` | Unit | Both Telegram + email fire, one failure doesn't block other |

### Eval Suite

```python
# tests/evals/test_email_rendering.py
def test_email_html_snapshot(snapshot):
    """Email HTML should match golden format."""
    deal = build_test_deal(origin="MCI", dest="LHR", price=300, drop=50)
    html = EmailNotifier()._render_deal_html(deal)
    assert snapshot == html

def test_email_subject_format(snapshot):
    """Subject line should follow pattern."""
    deal = build_test_deal(origin="MCI", dest="LHR", price=300)
    subject = EmailNotifier()._build_subject(deal)
    assert snapshot == subject
```

---

## Phase 3: Price History API + Trends

### Spec

New API endpoint returning daily median prices for a route over a date range.
Enables trend charts in the dashboard and helps users identify buying windows.

### API

```
GET /deals/history?route=MCI-LHR&days=90
```

Response:
```json
{
  "route": "MCI-LHR",
  "days": 90,
  "data_points": 45,
  "history": [
    {"date": "2026-06-01", "median_price": 500, "lowest_price": 350, "sample_count": 8},
    {"date": "2026-06-02", "median_price": 480, "lowest_price": 320, "sample_count": 6}
  ],
  "current_median": 450,
  "trend": "down",
  "trend_percent": -10.0
}
```

### Implementation

New method in `price_analysis.py`:
```python
async def get_price_history(
    session: AsyncSession,
    origin: str,
    destination: str,
    days: int = 90,
) -> dict:
    """Get daily median prices for a route."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = (
        select(
            func.date(FlightDeal.seen_at).label("date"),
            func.avg(FlightDeal.original_price_usd).label("avg_price"),
            func.min(FlightDeal.current_price_usd).label("lowest_price"),
            func.count().label("sample_count"),
        )
        .where(FlightDeal.origin == origin)
        .where(FlightDeal.destination == destination)
        .where(FlightDeal.seen_at >= cutoff)
        .group_by(func.date(FlightDeal.seen_at))
        .order_by(func.date(FlightDeal.seen_at))
    )
    ...
```

### Test Strategy

| Test | Type | What it covers |
|------|------|---------------|
| `test_price_history.py` | Unit | Returns correct data shape, empty history, single day |
| `test_price_history_trend.py` | Unit | Trend detection (up/down/flat) with known data |
| `test_price_history_endpoint.py` | Integration | API returns 200 with correct JSON shape |

---

## Phase 4: Slack/Discord Webhooks

### Spec

Webhook-based notifiers for Slack and Discord. Same `BaseNotifier` interface.
Configurable via `.env` with webhook URLs.

### Implementation

```
app/
  notifiers/
    slack.py       # SlackNotifier
    discord.py     # DiscordNotifier
```

Each is ~40 lines. Uses `httpx.AsyncClient` (already a dependency). Message
formatting adapted to each platform's rich message format (Slack blocks,
Discord embeds).

### Config

```
# Slack (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Discord (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### Test Strategy

| Test | Type | What it covers |
|------|------|---------------|
| `test_slack_notifier.py` | Unit | Payload format, rate limiting |
| `test_discord_notifier.py` | Unit | Embed format, color coding by deal type |
| `test_webhook_http_mock.py` | Unit | HTTP send with mocked httpx |

---

## Phase 5: PostgreSQL Support

### Spec

Production-ready PostgreSQL support alongside SQLite. Config-driven: swap
`DATABASE_URL` in `.env` and everything works. Alembic migrations for schema
management.

### Implementation

1. Add `asyncpg` and `alembic` to `requirements.txt`
2. Create `alembic.ini` and `alembic/` directory
3. Configure `env.py` for async migrations
4. Add `pool_size`, `max_overflow`, `pool_pre_ping` to engine config
5. Test with both SQLite and PostgreSQL in CI

### Test Strategy

| Test | Type | What it covers |
|------|------|---------------|
| `test_postgres_connection.py` | Integration | Connect, create tables, insert, query (opt-in) |
| `test_alembic_migrations.py` | Integration | Migration up/down works (opt-in) |
| `test_sqlite_compat.py` | Unit | All queries work with SQLite (existing tests) |

---

## Phase 6: Multi-City / Flexible Dates

### Spec

Extend the long weekend pattern to support:
- Multi-city itineraries (MCI→LHR→BCN→MCI)
- Flexible date ranges (±3 days from a target date)
- "Anywhere" mode — scan all destinations from home airport

### Implementation

New config section:
```yaml
app:
  flexible_dates:
    enabled: false
    range_days: 3  # ±3 days from target
  multi_city:
    enabled: false
    max_stops: 2
```

New utility functions in `app/utils/flexible_dates.py`:
```python
def expand_date_range(target_date: str, range_days: int = 3) -> list[str]:
    """Return all dates in [target - range, target + range]."""
    ...

def generate_multi_city_routes(
    home: str, destinations: list[str], max_stops: int = 2
) -> list[tuple[str, str, str]]:
    """Generate (origin, stop, destination) combinations."""
    ...
```

### Test Strategy

| Test | Type | What it covers |
|------|------|---------------|
| `test_flexible_dates.py` | Unit | Date range expansion, edge cases (month boundary) |
| `test_multi_city_routes.py` | Unit | Route generation, deduplication, max stops |
| `test_flexible_sweep.py` | Integration | Sweep with flexible dates (mocked) |

---

## Phase 7: User Auth + Personalization

### Spec

Multi-user support with per-user route lists, notification preferences, and
alert history. Session-based auth (no OAuth for MVP). Admin user manages
global config, regular users have their own route lists.

### Implementation

```
app/
  models/
    user.py        # User model (email, password hash, role)
  routes/
    auth.py        # Login, logout, register
  templates/
    auth/
      login.html
      register.html
```

**Dependencies:** `passlib[bcrypt]`, `python-jose[cryptography]` (JWT for session),
or use FastAPI's session middleware.

### Test Strategy

| Test | Type | What it covers |
|------|------|---------------|
| `test_auth_login.py` | Unit | Login with valid/invalid credentials |
| `test_auth_session.py` | Unit | Session expiry, protected routes |
| `test_user_preferences.py` | Unit | Save/load per-user route lists |
| `test_auth_integration.py` | Integration | Full login flow with DB |

---

## Eval Suite Architecture

### Directory Structure

```
tests/
  evals/
    __init__.py
    conftest.py              # Shared fixtures for evals
    test_dashboard_render.py # Snapshot tests for UI
    test_email_rendering.py  # Snapshot tests for email
    test_price_accuracy.py   # Price parsing accuracy
    test_alert_timing.py     # Alert threshold timing
    test_performance.py      # Benchmark key operations
```

### GEPA Self-Improvement Loop

The eval suite enables a **G**enerate → **E**valuate → **P**ropose → **A**dapt loop:

1. **Generate** — Run the system against real data (fli, SearchAPI) and collect
   outputs: prices, alerts, emails, dashboard renders. Store as golden snapshots
   in `tests/evals/snapshots/`.

2. **Evaluate** — On each change, compare new outputs against golden snapshots
   using `syrupy`. Failures surface as snapshot diffs:
   ```bash
   pytest tests/evals/ --snapshot-warn-unused
   ```

3. **Propose** — When an eval fails, the CI pipeline logs the diff and suggests
   a fix. For intentional changes (e.g., new deal type), update snapshots:
   ```bash
   pytest tests/evals/ --snapshot-update
   ```

4. **Adapt** — Update code, re-run evals, commit updated snapshots. The snapshot
   history becomes a changelog of how outputs evolved.

### CI Integration

```yaml
# In ci-cd.yml, add to test job:
- name: Run eval suite
  run: pytest tests/evals/ --snapshot-warn-unused -v
  env:
    SNAPSHOT_UPDATE: ${{ github.event_name == 'workflow_dispatch' && '1' || '0' }}
```

Eval failures are warnings by default (non-blocking), but can be promoted to
blocking for critical paths (price accuracy, alert delivery).

### Performance Benchmarks

```python
# tests/evals/test_performance.py
import pytest

pytestmark = pytest.mark.benchmark

def test_price_analysis_throughput(benchmark):
    """Should analyze 1000 prices in under 100ms."""
    prices = [random.uniform(100, 1000) for _ in range(1000)]
    result = benchmark(analyze_prices_batch, prices)
    assert result["p95_latency_ms"] < 100

def test_dashboard_render_time(benchmark):
    """Dashboard should render in under 200ms with 50 deals."""
    seed_deals(50)
    result = benchmark(lambda: client.get("/dashboard"))
    assert result.elapsed.total_seconds() < 0.2
```

---

## Implementation Order

```
Phase 1: Web UI Dashboard       ← HIGHEST VALUE, START HERE
Phase 2: Email Alerts           ← HIGH VALUE, LOW EFFORT
Phase 3: Price History + Trends ← MEDIUM VALUE, LOW EFFORT
Phase 4: Slack/Discord Webhooks ← MEDIUM VALUE, VERY LOW EFFORT
Phase 5: PostgreSQL Support      ← PRODUCTION READINESS
Phase 6: Multi-City / Flex Dates ← NICHE BUT POWERFUL
Phase 7: User Auth              ← PREMATURE, DEFER
```

Each phase is independent — they can be implemented in any order. Phases 1-4
can be parallelized across multiple PRs.

---

## Success Criteria

- [ ] Dashboard renders with real data, no console errors
- [ ] Email alerts deliver within 60 seconds of deal detection
- [ ] Price history endpoint returns correct data for any route
- [ ] Slack/Discord webhooks deliver with correct formatting
- [ ] PostgreSQL migration works with zero data loss
- [ ] Multi-city sweep detects deals across connected routes
- [ ] Eval suite runs in CI, snapshots are version-controlled
- [ ] Performance benchmarks stay within 2x of baseline
