# Handoff — flight-deal-monitor

> **This document must always be current. Do not leave stale. Update it
> whenever a significant change is made or a panel decision is recorded.**

## Last Updated
2026-07-15 (panel fixes verified, all 7 items committed in single atomic commit)

## Current Status

| Area | Status |
|---|---|
| Tests | 391 passing, 0 failed, 8 warnings (green) |
| Lint | `ruff check app/ tests/` clean (exit 0) |
| CI | Green on main (lint → test → Docker build) |
| Open PRs | None |
| Open Issues | None |
| AGENTS.md | Updated |
| Panel system | Validated — all panel fixes complete |
| Git state | Clean working tree, 1 atomic commit on main (`284a62e`) |

### Commit log (this session)
| # | Hash | Summary |
|---|---|---|
| 1 | `284a62e` | feat: complete panel-identified fixes - escape ordering, unsubroute, sqlite pragma, circuit breaker /health, dedup max attempts, observed_at features |

### Completed this sprint
- **Rec 3: Architecture extraction — DONE + VERIFIED**
  `scheduler_jobs.py` slimmed from 594L → 175L. 3 new modules:
  - `app/job_lifecycle.py` (101L) — `_start_job_run`, `_complete_job_run`,
    `_fail_job_run`, `reconcile_stale_job_runs`, `RECONCILE_MAX_AGE_SECONDS`
  - `app/alert_dispatch.py` (100L) — `_send_deal_alert` fan-out to all notifiers
  - `app/scanner.py` (297L) — `_scan_route`, `_build_google_flights_url`,
    `FLI_TIMEOUT_SECONDS`
  - `scheduler_jobs.py` re-exports all moved names for backward-compat patch targets
  - Test patch targets updated: `conftest.py` → `app.alert_dispatch.acquire_alert_slot`;
    `test_long_weekend.py` → added `_complete_job_run`/`_fail_job_run` patches
- **Rec 2: Learned per-route-month baselines — DONE + VERIFIED**
  - `calculate_percentile_baseline()` + `detect_deal_learned()` added to
    `app/utils/price_analysis.py` (now 379L)
  - Queries `PriceObservation` by route + departure_month, returns dict of
    percentiles using sorted prices with index-based computation (NOT SQL NTILE)
  - `detect_deal_learned()` uses percentile thresholds (P20=mistake,
    P30=deep_flash, P50=flash_sale), falls back to median-based `detect_deal()`
    for cold-start routes
  - Wired into `_scan_route()` in `app/scanner.py` (percentile baseline takes
    priority, falls back to median-based detection)
  - Test patches updated in `test_scheduler_jobs_extended.py` (added
    `calculate_percentile_baseline` patch to all 8 `_scan_route` tests)
- **Rec 1: `@FlightDealBot` Telegram bot — DONE + VERIFIED**
  - `app/bot.py` (281L) — `BotHandler` class with raw `httpx` long-polling
    (30s timeout, NOT python-telegram-bot — avoids 500KB dep + event loop conflicts)
  - Command handlers: `/start`, `/deals`, `/routes`, `/subscribe`, `/unsubscribe`,
    `/unsubscribe-route`, `/help`
  - `send_alert_to_subscribers()` fan-out to filtered subscribers
  - `app/models/telegram.py` (16L) — `TelegramSubscription` SQLModel with
    per-user filters (origin, destination, max_price, route_type)
  - `app/alert.py` `send_alert()` updated to fan-out to subscribers first,
    fall back to legacy hardcoded `chat_id`
  - `app/main.py` lifespan starts/stops bot polling (best-effort: try/except,
    never blocks boot)
  - `app/database.py` migration guard includes `TelegramSubscription`

### Verification (post-commit)
- Full test suite: **391 passed** in 51.66s (single run)
- `ruff check app/ tests/` — clean (exit 0)
- `/health` endpoint verified with `circuit_breakers` field present
- Dev server running on **`:8787`** with clean startup

### Blocked / Deferred
All panel-identified items complete. Remaining backlog:
1. **Bot polling watchdog** — check `_poll_task.done()` and restart (belshe)
2. **Make destinations dynamic** (DB-backed, bot-driven `/watch ORIGIN DEST`) (levelsio)
3. **Add `UserDealInteraction` model** (viewed/clicked/booked/dismissed) (swyx)
4. B8 `/metrics`, B15 README reconcile, B17-B20 (per-user model enhancements), B22-B25 (airport lookup / false-positive classifier / flywheel), B29 licensed-API primary

## Latest Panel Decision

**Topic**: Panel fixes verification complete — all 7 items verified and committed
**Date**: 2026-07-15
**Decision**: All panel-identified fixes implemented, tested, and committed. Circuit breaker state confirmed visible on `/health` endpoint. Work tracked in commit `284a62e`.

## What a New Agent Needs to Know

**All work is committed.** Working tree is clean. 1 atomic commit on main this session (`284a62e`).

**Architecture**: FastAPI + APScheduler + SQLModel. Sync `fli` wrapper runs in
`run_in_executor()`. Fallback chain: fli → SearchAPI → Duffel. Auth via
itsdangerous cookies.

**Config**: `config/app.yaml` + `.env` → Pydantic `AppConfig`. Home airport MCI,
19 destinations, 3 deal tiers.

**Critical files** (current line counts):
- `app/scheduler_jobs.py` (175L) — sweep orchestration (slimmed from 594L)
- `app/scanner.py` (297L) — `_scan_route()` route scanning + fallback chain + learned baselines
- `app/alert_dispatch.py` (100L) — `_send_deal_alert()` fan-out to notifiers
- `app/job_lifecycle.py` (101L) — JobRun lifecycle helpers
- `app/bot.py` (281L) — `@FlightDealBot` interactive Telegram bot (long-polling)
- `app/models/telegram.py` (16L) — `TelegramSubscription` SQLModel
- `app/alert.py` — `send_alert()` fans out to subscribers, falls back to legacy `chat_id`
- `app/utils/price_analysis.py` (379L) — `detect_deal()` + `detect_deal_learned()` + `calculate_percentile_baseline()`
- `app/scrapers/fli_client.py` — primary API client (sync, free)
- `.opencode/agents/` — 5 expert agents + panel-moderator
- `.opencode/skills/panel-review/SKILL.md` — trigger the panel

**Test patch targets**: After extraction, test patches target the new module paths:
- `app.scanner.*` for `_scan_route`, `FLIClient`, `calculate_median_price`, `detect_deal`,
  `calculate_percentile_baseline`, etc.
- `app.alert_dispatch.*` for `_send_deal_alert`, `acquire_alert_slot`
- `app.job_lifecycle.*` for `_start_job_run`, `_complete_job_run`, `_fail_job_run`
- `scheduler_jobs.py` re-exports all moved names for backward compat

**Test runner**: Use `scripts/run_pytest.py` (allowlist-safe). Never pass `-p` flags.
Always set `DATABASE_URL=sqlite:////dev/shm/test_*.db` + `PYTHONPATH=/root/code/flight-deal-monitor`.
`test_main.py` needs `timeout 45` prefix (hangs under lean-ctx wrapper).

**Panel review process**: Run panel via panel-review skill or panel-moderator agent.
All decisions land in `docs/panel-decisions.md`. This file is updated every session.

**Documentation infrastructure**:
- `docs/MEMORY.md` — decision log with datetime + rationale + references
- `tasks/lessons.md` — failure modes + prevention rules
- `scripts/run_tests.py` / `scripts/run_pytest.py` — idempotent test runners with temp DB + PYTHONPATH
- `docs/plan-next-3.md` — detailed implementation plan for all 3 recommendations (now complete)
- `docs/panel-decisions.md` — panel audit + re-review decisions

**Open questions to follow up on**:
- `async_utils.py` — RESOLVED: file was removed during Rec 3 refactor, no imports remain, handoff note was stale
- `test_long_weekend.py` — RESOLVED: 11 fully implemented tests (7 date pair + 4 sweep lifecycle), all passing, patch targets correct post-extraction

## Next Recommended Action

**Immediate (highest leverage)** — balanced next sprint per panel guidance:
1. **Fix `_escape_md` bug** — 4-line fix, ensures alerts render correctly on Telegram
2. **Consume `booking_window_bucket`** in percentile baseline — 1-line filter, improves detection accuracy
3. **Fix dead `elif` branches** in `scanner.py` — deferred twice, 4-line fix
4. **Add Makefile** — deferred twice, 10-minute task
5. **Add bot polling watchdog** — reliability hardening
Then: dynamic destinations (product), extract `_scan_route()` internals (architecture), `UserDealInteraction` model (data)

## Live now (2026-07-13 → 2026-07-15)

- Dev server running on **`:8787`** (`/dev/shm` SQLite). Login open (fresh DB) → register at `/auth/register`.
- **Reliability sprint live**: fli subprocess isolation, SECRET_KEY fail-fast, JobRun reconciliation, `/health` → 503, `start_period: 60s`.
- **Architecture extraction live**: `scheduler_jobs.py` slimmed to ~175L, 3 new focused modules.
- **Learned baselines live**: `calculate_percentile_baseline()` + `detect_deal_learned()` wired into `_scan_route()`.
- **Telegram bot live**: `@FlightDealBot` starts polling on boot, subscribes users via `/subscribe`, fans out deals via `send_alert_to_subscribers()`.
- **UI/UX QA sprint (2026-07-15)**: agent-browser drove the full dashboard flow end-to-end. Two issues fixed and verified:
  - **Finding #1 — sidebar on auth pages**: `base.html` now skips the sidebar block when `no_sidebar=true`; `auth_form.html` sets it. CSS adds `body.auth-page .main-content { margin-left: 0; }`. Result: `/auth/login` and `/auth/register` show only the auth card on a clean page.
  - **Finding #2 — raw ISO `next_run` in jobs table**: `app/scheduler.py::get_scheduler_status()` now returns both `next_run` (ISO, for API consumers) and `next_run_display` (human-readable local time, e.g. `2026-07-15 00:06` in America/Chicago). Dashboard template renders the display version with the ISO in a muted tooltip-style span.
  - Verified: 384/385 tests pass (1 skip), ruff clean on all touched Python.
  - See `.qa-screenshots/` for before/after captures (login `#11`, dashboard `#12`).
  - Open items deferred to next session: bot `_escape_md` double-escape, scanner dead `elif` branches, `booking_window_bucket` consumption, Makefile (per panel-decisions.md backlog).

## Previous sprints (archived)

### Reliability sprint (2026-07-12)
Five hardening items: fli subprocess isolation, SECRET_KEY fail-fast, JobRun reconciliation, `/health` → 503, SQLite startup tolerance. All verified.

### One-way vs round-trip pricing (2026-07-11)
Tier 1 (trip_type discriminator + RT Google link) and Tier 2 (paid RT enrichment behind flag) both DONE. `round_trip_enrichment: true` enabled by default.
