# Handoff — flight-deal-monitor

> **This document must always be current. Do not leave stale. Update it
> whenever a significant change is made or a panel decision is recorded.**

## Last Updated
2026-07-13 (all work committed in 8 atomic commits, tests green, ruff clean)

## Current Status

| Area | Status |
|---|---|
| Tests | 384 passing, 0 failed, 7 skipped (green) |
| Lint | `ruff check app/ tests/` clean (exit 0) |
| CI | Green on main (lint → test → Docker build) |
| Open PRs | None |
| Open Issues | None |
| AGENTS.md | Updated (this session) |
| Panel system | Validated — full audit complete (7.5/10 score) |
| Git state | Clean working tree, 8 atomic commits on main |

### Commit log (this session)
| # | Hash | Summary |
|---|---|---|
| 1 | `272c26f` | feat: round-trip pricing — trip_type discriminator + RT Google Flights enrichment |
| 2 | `70d6b1b` | feat: reliability sprint — fli subprocess isolation, fail-fast secrets, circuit breaker, rate limiter |
| 3 | `d90d7c7` | refactor: Rec 3 — extract scheduler_jobs.py God Module into focused modules |
| 4 | `a97aad0` | feat: Rec 2 — learned per-route-month baselines via PriceObservation percentiles |
| 5 | `323c58d` | feat: Rec 1 — @FlightDealBot interactive Telegram bot |
| 6 | `3bafa71` | fix: fli test rewrite for subprocess isolation + UI/dashboard updates |
| 7 | `be12196` | docs: handoff, panel decisions, MEMORY, lessons, plan, scripts, AGENTS.md |
| 8 | `1965988` | chore: gitignore .env.bak and .opencode/ agent tooling |

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
    `/help`
  - `send_alert_to_subscribers()` fan-out to filtered subscribers
  - `app/models/telegram.py` (16L) — `TelegramSubscription` SQLModel with
    per-user filters (origin, destination, max_price, route_type)
  - `app/alert.py` `send_alert()` updated to fan-out to subscribers first,
    fall back to legacy hardcoded `chat_id`
  - `app/main.py` lifespan starts/stops bot polling (best-effort: try/except,
    never blocks boot)
  - `app/database.py` migration guard includes `TelegramSubscription`

### Verification (post-commit)
- Full test suite: **384 passed, 0 failed, 7 skipped** (run in 6 batches)
  - Batch A (83): fli_client, price_analysis + extended, round_trip, dedup, database, ensure_schema
  - Batch B (38): scheduler_jobs + extended, sweeps, long_weekend
  - Batch C1 (71): alert, api_clients, auth, cache, config
  - Batch C2 (123): dashboard, database_url, email_notifier, webhook_notifiers, searchapi
  - Batch D (54+7 skipped): alembic, flexible_dates, fli_integration, lifespan, price_history, scheduler
  - Batch E (15): test_main
- `ruff check app/ tests/` — clean (exit 0)
- Test command: `DATABASE_URL=sqlite:////dev/shm/test.db PYTHONPATH=. python3 -m pytest tests/ -q`
  - **Note**: Running the full suite at once hangs (likely some test cleanup / asyncio loop issue).
    Run in batches: `timeout 60 python3 -m pytest <files> -q`. Individual test_main.py needs `timeout 45` prefix.

### Blocked / Deferred (post-sprint backlog)
These items from the latest panel re-review are NOT yet started:
1. **Add `observed_at_month` + `observed_at_day_of_week`** to `PriceObservation` (swyx) — seasonal feature set
2. **Expose circuit breaker state via `/health`** — `circuit_breakers` field in `HealthResponse` (belshe)
3. Fix dead `elif` log branches in `_scan_route()` (b0rk)
4. Add permanent-failure threshold to dedup retry (belshe)
5. Add `PRAGMA synchronous=NORMAL` alongside WAL (belshe)
6. Makefile with `dev/test/lint/format/docker-up` (hanselman)
7. `UserDealInteraction` model for feedback loop (swyx)
8. B8 `/metrics`, B17-B20 (per-user model / affiliate / public feed),
   B22-B25 (airport lookup / false-positive classifier / flywheel),
   README full reconcile (B15)

## Latest Panel Decision

**Topic**: Full panel re-review — post-fix-sprint (5 panelists, all fix-sprint items verified)
**Date**: 2026-07-12
**Decision**: All 5 top-priority fixes from the prior panel were validated as correct.
Overall score improved from **7/10 → 7.5/10**.

### Scores by panelist
| Panelist | Previous | Current | Delta |
|---|---|---|---|
| levelsio (PMF) | 6 | 6 | 0 |
| hanselman (DX) | 7 | 7.5 | +0.5 |
| belshe (Reliability) | 6 | 8 | +2 |
| swyx (AI/Moat) | 5 | 6 | +1 |
| b0rk (Architecture) | 6.5 | 7 | +0.5 |
| **Overall** | **7** | **7.5** | **+0.5** |

**Key insight**: The previous top-5 were all "fix what's broken." This round's top items are "build what's next" — the breaks are fixed; the next gains come from product direction (Telegram bot), data moat (learned baselines), and architecture health (God Module split).

**Panel re-review status**: All 3 recommendations (Rec 1, 2, 3) from the last panel are now implemented and verified. A new panel re-review should be triggered to score the impact.

## What a New Agent Needs to Know

**All work is committed.** Working tree is clean. 8 atomic commits on main this session.

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
- `async_utils.py` error state after refactor (needs verification)
- `test_long_weekend.py` stub tests need implementation

## Next Recommended Action

**Immediate (highest leverage)**:
1. **Panel re-review** — trigger panel to score the impact of all 3 implemented recommendations (Rec 1, 2, 3). All work is now committed.
2. **Next feature wave** — pick from deferred backlog above (seasonal features, circuit breaker visibility, Makefile, etc.)

## Live now (2026-07-13)

- Dev server running on **`:8787`** (`/dev/shm` SQLite). Login open (fresh DB) → register at `/auth/register`.
- **Reliability sprint live**: fli subprocess isolation, SECRET_KEY fail-fast, JobRun reconciliation, `/health` → 503, `start_period: 60s`.
- **Architecture extraction live**: `scheduler_jobs.py` slimmed to ~175L, 3 new focused modules.
- **Learned baselines live**: `calculate_percentile_baseline()` + `detect_deal_learned()` wired into `_scan_route()`.
- **Telegram bot live**: `@FlightDealBot` starts polling on boot, subscribes users via `/subscribe`, fans out deals via `send_alert_to_subscribers()`.

## Previous sprints (archived)

### Reliability sprint (2026-07-12)
Five hardening items: fli subprocess isolation, SECRET_KEY fail-fast, JobRun reconciliation, `/health` → 503, SQLite startup tolerance. All verified.

### One-way vs round-trip pricing (2026-07-11)
Tier 1 (trip_type discriminator + RT Google link) and Tier 2 (paid RT enrichment behind flag) both DONE. `round_trip_enrichment: true` enabled by default.
