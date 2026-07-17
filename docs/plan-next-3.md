# Implementation Plan: Top 3 Remaining Recommendations

**Created**: 2026-07-12
**Context**: Post-panel-re-review (7→7.5/10). The 4 reliability fixes are done. These are the next 3 leverage items.

---

## Recommendation 1: Ship `@FlightDealBot` Telegram Bot

### Current state
- `app/alert.py` defines `TelegramBot` class — **outbound only** (push alerts to a hardcoded `chat_id`)
- Uses raw `httpx` calls to `https://api.telegram.org/bot{token}/sendMessage`
- Not a real "bot" — users can't interact with it
- `requirements.txt` has NO `python-telegram-bot` dependency
- Single global `telegram_bot = TelegramBot()` singleton, not behind `BaseNotifier`
- The bot token + chat_id are in `EnvConfig` (`config.py:163-164`)

### What "ship the bot" means
Transform from a one-way alert pusher into an interactive Telegram bot where users can:
- `/start` — register their chat ID for alerts
- `/deals` — see latest deals (uses existing `/deals` API query logic)
- `/routes` — see monitored routes
- `/subscribe MCI LHR` — subscribe to specific route alerts
- `/help` — show commands
- The bot still receives outbound deal alerts via the existing fan-out, but now users self-register instead of hardcoding a chat_id

### Architecture decision: raw httpx vs python-telegram-bot
**Recommendation: raw httpx (no new dependency)**

Rationale:
- The existing `TelegramBot` already works with raw httpx
- `python-telegram-bot` v21 is a heavyweight dependency (~500KB) with its own event loop management that conflicts with the existing asyncio + APScheduler setup
- We only need `getUpdates` (polling) + `sendMessage` — both are simple HTTP calls
- FastAPI lifespan can run a polling loop as a background task alongside the scheduler
- Zero risk of event loop conflicts

### Steps

#### 1.1 — Create `app/bot.py` (new file, ~200 lines)
- `TelegramBotHandler` class with:
  - `__init__(self, token, session_factory)` — stores token + async session factory
  - `async def start_polling(self)` — long-poll loop: `GET /getUpdates?offset=N&timeout=30`
  - `async def stop_polling(self)` — cancel the poll task
  - `async def handle_update(self, update: dict)` — dispatch by command
  - `async def cmd_start(update)` — register chat_id in DB
  - `async def cmd_deals(update)` — query latest 5 deals, format, send
  - `async def cmd_routes(update)` — list monitored routes from config
  - `async def cmd_subscribe(update, origin, destination)` — store subscription
  - `async def cmd_help(update)` — list commands
- Each command is a small async method; no complex routing framework

#### 1.2 — Create `app/models/telegram.py` (new file, ~30 lines)
- `TelegramSubscription(SQLModel, table=True)`:
  - `id: int | None` (PK)
  - `chat_id: str` (indexed)
  - `origin: str | None` (NULL = all)
  - `destination: str | None` (NULL = all)
  - `created_at: datetime`
  - `is_active: bool = True`

#### 1.3 — Wire polling into `app/main.py` lifespan
- In `lifespan()`, after scheduler start, start the bot polling as `asyncio.create_task(bot.start_polling())`
- On shutdown, cancel the task
- Gate behind `config.env.telegram_bot_token` being non-empty
- Optional `TELEGRAM_BOT_ENABLED=true` env var (default false for backward compat)

#### 1.4 — Update `app/alert.py` `TelegramBot.send_alert()`
- Query `TelegramSubscription` for active `chat_id` values
- Send alert to ALL subscribed chat IDs (fan-out), not just one hardcoded `chat_id`
- Keep the existing `send_error_alert()` to a single admin chat_id (configurable via `TELEGRAM_ADMIN_CHAT_ID`)

#### 1.5 — Tests
- `tests/test_bot.py`:
  - `test_cmd_start_registers_chat_id` — mock getUpdates, assert DB row
  - `test_cmd_deals_returns_deals` — seed deals, mock sendMessage, assert response
  - `test_cmd_subscribe_stores_subscription` — parse `/subscribe MCI LHR`, assert DB row
  - `test_send_alert_fans_out_to_subscribers` — seed 3 subscriptions, assert 3 sendMessage calls
  - `test_polling_handles_invalid_update_gracefully` — malformed update dict, no crash

#### 1.6 — Config changes
- Add `telegram_admin_chat_id: str = ""` to `EnvConfig`
- Add `telegram_bot_enabled: bool = False` to `EnvConfig`
- Add to `.env.example`

### Risk
- **Low**: New file, new model table. No changes to existing sweep logic. The alert fan-out change (1.4) touches `alert.py` but is isolated to the `send_alert` method.
- **Rollback**: Set `TELEGRAM_BOT_ENABLED=false` — reverts to one-way alert-only mode.

---

## Recommendation 2: Learned Per-Route-Month Baselines (percentile_cont)

### Current state
- `calculate_median_price()` at `price_analysis.py:33-72`:
  - Queries `PriceObservation.price_usd` for route+trip_type, last 30 days
  - Loads ALL prices into Python memory, sorts, picks middle element
  - Returns `None` if < `min_baseline_samples` (5)
- `detect_deal()` at `price_analysis.py:165-181`:
  - Static thresholds: `price_drop_percent >= 0.70 → mistake_fare`, `>= 0.65 → deep_flash`, `>= 0.50 → flash_sale`
  - Applies a route multiplier (domestic 1.0, transatlantic 0.8, etc.) to the median
  - **Route-agnostic**: same threshold for MCI→JFK (domestic) and MCI→LHR (transatlantic)
- The 4 ML feature columns exist but are **unconsumed** — nothing reads `days_until_departure`, `departure_month`, etc.

### What "learned baseline" means
Replace the simple 30-day median with a **per-route, per-month, per-booking-window percentile** query. Instead of "median of all prices for this route in 30 days", compute "what's the 25th percentile price for MCI→LHR in December for the 22-60d booking window?"

This makes deal detection seasonal (December MCI→LHR has a different baseline than July) and booking-window-aware (last-minute fares behave differently from advance-purchase fares).

### SQLite constraint
- SQLite does NOT have `PERCENTILE_CONT` (that's Postgres-only)
- SQLite DOES support window functions (since 3.25.0, 2018) and `NTILE`
- **Approach**: Use `NTILE(100)` window function to bucket prices into 100 ranks, then select the rank that corresponds to the desired percentile (e.g., rank 25 for P25)
- This is a single SQL query, no Python-side sorting needed
- When migrating to Postgres, swap to native `PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY price_usd)`

### Steps

#### 2.1 — Add `calculate_route_baseline()` to `price_analysis.py` (~60 lines)
- New function signature:
  ```python
  async def calculate_route_baseline(
      session: AsyncSession,
      origin: str,
      destination: str,
      departure_date: str,
      trip_type: str = "one_way",
      percentile: float = 0.25,
      min_samples: int = 5,
  ) -> tuple[float | None, str]:
      """Returns (baseline_price, source) where source is 'learned' or 'median_fallback'."""
  ```
- Parse `departure_date` → get `departure_month` + `days_until_departure` → `booking_window_bucket`
- Query: `SELECT price_usd, NTILE(100) OVER (ORDER BY price_usd) as pct FROM price_observations WHERE origin=? AND destination=? AND departure_month=? AND booking_window_bucket=? AND trip_type=?`
- Filter to last 90 days (not 30 — seasonal needs more data)
- If sample count ≥ `min_samples` AND the bucket has at least 3 samples → return the price at `NTILE` rank closest to `percentile * 100`
- If insufficient samples in the bucket → fall back to the broader median (current `calculate_median_price` logic)
- Return `(baseline, "learned")` or `(baseline, "median_fallback")` so callers know which was used

#### 2.2 — Add `detect_deal_learned()` to `price_analysis.py` (~30 lines)
- New function:
  ```python
  async def detect_deal_learned(
      current_price: float,
      baseline_price: float,
      baseline_source: str,
      origin: str,
      destination: str,
  ) -> tuple[bool, str | None]:
  ```
- If `baseline_source == "learned"`: use **percentile-based thresholds** (price below P25 = deal, below P10 = mistake, below P15 = deep_flash)
- If `baseline_source == "median_fallback"`: keep existing static thresholds (50/65/70%)
- This cleanly handles cold-start (not enough data for learned → use old approach)

#### 2.3 — Wire into `_scan_route()` at `scheduler_jobs.py`
- Replace the `calculate_median_price()` call (line ~435) with `calculate_route_baseline()`
- Replace the `detect_deal()` call (line ~450) with `detect_deal_learned()`
- No other changes to the scan flow

#### 2.4 — Config: add percentile thresholds
- In `DealThresholds` (config.py), add:
  - `learned_flash_sale_percentile: float = 0.25` (P25)
  - `learned_deep_flash_percentile: float = 0.15` (P15)
  - `learned_mistake_fare_percentile: float = 0.10` (P10)
- Keep existing static thresholds as fallback

#### 2.5 — Tests (TDD — write tests first)
- `tests/test_learned_baseline.py` (new file):
  - `test_calculate_route_baseline_with_enough_data` — seed 20 PriceObservations for MCI→LHR in December, 22-60d bucket → returns P25 price
  - `test_calculate_route_baseline_falls_back_to_median` — seed 3 obs (below min_samples) → returns median, source="median_fallback"
  - `test_calculate_route_baseline_no_data` — 0 obs → returns None
  - `test_detect_deal_learned_below_p25` — price at P20 → deal=True, type="flash_sale"
  - `test_detect_deal_learned_below_p10` — price at P5 → deal=True, type="mistake_fare"
  - `test_detect_deal_learned_median_fallback_uses_static_thresholds` — baseline_source="median_fallback" → uses 50/65/70%
  - `test_ntile_query_correctness` — seed exactly 100 prices, assert NTILE assigns ranks 1-100

### Risk
- **Medium**: Changes deal detection logic — could change which flights are flagged as deals.
- **Mitigation**: Learned baseline only activates when sufficient data exists (≥5 samples in the route+month+bucket). Until then, the existing static threshold approach is used. This is a safe progressive enhancement.
- **Rollback**: Set `min_samples` to a very high number (e.g., 9999) — always falls back to median.

---

## Recommendation 3: Extract `ScannerService` from `scheduler_jobs.py`

### Current state
`scheduler_jobs.py` is 594 lines with **7 distinct responsibilities** in one file:

| Responsibility | Lines | Functions |
|---|---|---|
| Job run lifecycle | ~60 | `_start_job_run`, `_complete_job_run`, `_fail_job_run` |
| Stale job reconciliation | ~30 | `reconcile_stale_job_runs` |
| Sweep orchestration | ~120 | `run_regular_sweep`, `run_mistake_sweep`, `run_long_weekend_sweep`, `run_cleanup` |
| Route scanning | ~200 | `_scan_route` (the big one) |
| Alert dispatch | ~80 | `_send_deal_alert` |
| URL building | ~20 | `_build_booking_url` (Kayak deep link) |
| Fli timeout constant | ~5 | `FLI_TIMEOUT_SECONDS` |

Health complexity scores: `_scan_route` w=74.0, `run_mistake_sweep` w=23.0, `_send_deal_alert` w=18.0.

### Extraction plan

Split into 4 focused modules. The goal is that `scheduler_jobs.py` becomes pure orchestration (just the sweep loops + job run tracking), with each piece independently testable.

#### 3.1 — `app/scanner.py` (new, ~250 lines)
Extract from `_scan_route()`:
```python
class ScannerService:
    """Scan a route for flight deals: cache → scrape → detect → persist."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def scan_route(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        route_suffix: str = "",
    ) -> list[FlightDeal]:
        # The full _scan_route logic moves here
```

Also move:
- `_build_booking_url()` → `scanner.py` (private method)
- `FLI_TIMEOUT_SECONDS` → `scanner.py`
- The cache check, fli subprocess call, circuit-breaker-gated fallback chain, flight parsing, deal detection, price observation recording — all move into `ScannerService.scan_route()`

#### 3.2 — `app/alert_dispatch.py` (new, ~100 lines)
Extract from `_send_deal_alert()`:
```python
class AlertDispatcher:
    """Fan-out deal alerts to all configured notifiers + record AlertHistory."""

    @staticmethod
    async def dispatch(session: AsyncSession, deal: FlightDeal) -> tuple[int, int]:
        # The full _send_deal_alert logic moves here
```

Also move:
- The `acquire_alert_slot()` gate
- The `asyncio.gather` fan-out to telegram/email/slack/discord
- The `delivered_any` computation + `AlertHistory` recording

#### 3.3 — `app/job_lifecycle.py` (new, ~80 lines)
Extract:
- `_start_job_run()`, `_complete_job_run()`, `_fail_job_run()`
- `reconcile_stale_job_runs()`
- `RECONCILE_MAX_AGE_SECONDS`

#### 3.4 — Slim `scheduler_jobs.py` (~140 lines, down from 594)
After extraction, this file contains ONLY:
- `run_regular_sweep()` — loop over origins×destinations×dates, call `ScannerService.scan_route()`, call `AlertDispatcher.dispatch()`, track `JobRun`
- `run_mistake_sweep()` — same pattern
- `run_long_weekend_sweep()` — same
- `run_cleanup()` — call `cleanup_expired_deals()`
- Imports from `scanner.py`, `alert_dispatch.py`, `job_lifecycle.py`

### Steps

#### Step 1: Extract `job_lifecycle.py` (lowest risk)
- Move `_start_job_run`, `_complete_job_run`, `_fail_job_run`, `reconcile_stale_job_runs`, `RECONCILE_MAX_AGE_SECONDS` to `app/job_lifecycle.py`
- Update imports in `scheduler_jobs.py` and `main.py`
- Run existing tests — should pass with no logic changes

#### Step 2: Extract `alert_dispatch.py`
- Move `_send_deal_alert` body to `AlertDispatcher.dispatch()`
- Update `scheduler_jobs.py` to call `AlertDispatcher.dispatch()`
- Run existing `test_scheduler_jobs.py` + `test_scheduler_jobs_extended.py` — should pass

#### Step 3: Extract `scanner.py`
- Move `_scan_route` body to `ScannerService.scan_route()`
- Move `_build_booking_url`, `FLI_TIMEOUT_SECONDS`
- Update `scheduler_jobs.py` to instantiate `ScannerService(session)` and call `.scan_route()`
- This is the riskiest extraction (200 lines of logic) — run full test suite

#### Step 4: Verify
- `ruff check app/ tests/`
- Full test suite (all 116+ tests)
- Dev server smoke test

### Risk
- **Medium**: Pure refactor — no behavior changes intended. Risk is import errors or missed dependencies.
- **Mitigation**: Extract in order of risk (job_lifecycle first, scanner last). Run tests after each extraction. No new logic.
- **Rollback**: Revert to single `scheduler_jobs.py` (git checkout).

---

## Execution order recommendation

1. **Rec 3 first (ScannerService extraction)** — this makes Rec 1 and Rec 2 easier to implement because the scan logic is cleanly isolated
2. **Rec 2 (learned baselines)** — modifies the scanner, which is now a clean module
3. **Rec 1 (Telegram bot)** — new feature, doesn't touch scan logic

**Estimated effort**:
- Rec 3: 2-3 hours (mechanical refactor)
- Rec 2: 3-4 hours (SQL query + TDD)
- Rec 1: 4-6 hours (new bot, model, tests)
- Total: 9-13 hours

---

## Dependencies
- No new pip packages needed for any of the 3 (using raw httpx for Telegram, SQLite NTILE for percentiles, pure Python for refactor)
- All 3 are independently shippable
