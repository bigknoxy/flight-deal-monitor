# Handoff — flight-deal-monitor

> **This document must always be current. Do not leave stale. Update it
> whenever a significant change is made or a panel decision is recorded.**

## Last Updated
2026-07-19 (full panel re-rating after reliability fixes; app avg **8.0/10 (+0.8)** vs 2026-07-19; bot-watchdog P0 CLOSED; scheduler job store separated)

## Current Status

| Area | Status |
|---|---|
| Tests | 485 passing, 8 skipped (test_bot_watchdog.py +4, test_scheduler_jobstore.py +6, test_flexible_dates_and_db.py +22) |
| Lint | `ruff check app/ tests/` clean (exit 0) |
| CI | Green on main (lint → test → Docker build) |
| Open PRs | None |
| Open Issues | None — all prior P1s + bot-watchdog P0 CLOSED in code |
| AGENTS.md | Updated |
| Panel system | Specialized agents in `.opencode/agents/*.md` (no model pin → default poolside/laguna-m.1); `opencode.json` gpt-4o override removed 2026-07-19. Task-tool `subagent_type` enum uses a separate built-in (gpt-4o) — use opencode native agent runtime, not the Task tool |
| Git state | Clean working tree, latest commit on main (`6756449`) |

### Prior P1 backlog — all CLOSED (verified in code)
| Item | Status | Evidence |
|---|---|---|
| Single-source-of-truth booking label | **CLOSED** | `BOOKING_PROVIDER_NAME = "Kayak"` (`config.py:19`) → `templates/__init__.py:19` |
| Kayak link-health smoke test | **CLOSED** | `tests/test_kayak_client.py` + scheduler extended suite |
| `booking_window_bucket` in `calculate_percentile_baseline()` | **CLOSED** | `price_analysis.py:249-250`; `test_scopes_by_booking_window_bucket` |
| Bot polling watchdog (was P0) | **CLOSED** | `app/bot.py:107-132` `_watchdog_loop` + test_bot_watchdog.py |
| Scheduler job store shared SQLite file (SPOF) | **CLOSED** | `app/scheduler.py:39-44` + `config.py scheduler_jobstore_url` + test_scheduler_jobstore.py |

### Scope decision (user)
Monetization / multi-user DB migration is **OUT OF SCOPE** — personal/family tool only.
Panel's remaining owner-facing suggestions (see panel-decisions.md 2026-07-19 (2)):
personal deal-history/seasonal insights, mobile Telegram actionability, `/metrics`
observability, optional WAL/backup for job-store. None are blockers.

### Commit log (this session)
| # | Hash | Summary |
|---|---|---|
| 1 | `eee3fbb` | fix: fli enum/None-price crashes + switch booking links to Kayak (relabel UI/README, TDD, backfill 986 rows) |

### Completed this sprint
- **Rec 3: Architecture extraction — DONE + VERIFIED**
  `scheduler_jobs.py` slimmed from 594L → 175L. 3 new modules:
  - `app/job_lifecycle.py` (101L) — `_start_job_run`, `_complete_job_run`,
    `_fail_job_run`, `reconcile_stale_job_runs`, `RECONCILE_MAX_AGE_SECONDS`
  - `app/alert_dispatch.py` (100L) — `_send_deal_alert` fan-out to all notifiers
  - `app/scanner.py` (297L) — `_scan_route`, `_build_booking_url` (Kayak deep link;
    Google Flights deep-link params deprecated 2026), `FLI_TIMEOUT_SECONDS`
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

### 2026-07-16 — UI empty-data investigation (ROOT CAUSE FOUND + FIXED)
**Symptom**: Dashboard showed no deals despite scheduler running.
**Root cause**: `app/scrapers/fli_client.py` — the primary (free) fli source's
subprocess output crashed at `json.dumps()` because fli returns `arrival_airport`
as an `Airport` **enum** (non-serializable). Every fli search failed → fell through
to paid providers (no real keys) → zero deals recorded. A secondary crash:
`f"{result.price:.2f}"` raised `NoneType.__format__` for results with `price=None`,
killing whole-route conversion.
**Fixes applied + COMMITTED (`eee3fbb`)**:
- `fli_client.py`: added `_json_default()` (coerces Enum→.value) used in the
  subprocess `print(json.dumps(..., default=_json_default))`; guarded `None` price
  → `0.0`; wrapped per-result `_to_dict()` in try/except so one bad result can't
  kill a route. `ruff` clean.
- Server restarted (detached via `/dev/shm/fdm_launch.sh`); verified `/deals` now
  returns **986 deals** (was 0), `/health` 200, scheduler running.
**Config gaps (NOT code bugs, need real credentials in `.env`)**:
- `TELEGRAM_BOT_TOKEN` is placeholder `test_bot_token` → bot 404s (`/bot<token>`
  URL format is correct; just needs a real token). Same for Slack/Discord webhooks
  (test endpoints, 405/302). These are env-config, not code.
- `SECRET_KEY` still insecure default `change-me-in-production` — set before any
  real deploy (forgeable session cookies).
**Next**: commit the two fli_client fixes; set real API credentials + SECRET_KEY.

## Latest Panel Decision

**Topic**: FULL AUDIT & REVIEW (production readiness, architecture, AI/ML, DX, business)
**Date**: 2026-07-16
**Decision**: **APPROVED for single-instance unattended deployment ONCE the bot polling
watchdog (P0) lands.** Re-audit corrected three stale "deferred bug" claims:
- `_escape_md` double-escape bug → FALSE POSITIVE (alert.py/bot.py escape only dynamic
  values; Markdown built into literal — correct).
- dead `elif` branches in scanner.py → FALSE (already fixed in prior sprint).
- `booking_window_bucket` unconsumed → TRUE (written in price_analysis.py:128-134, never
  filtered in calculate_percentile_baseline()).
- Makefile "missing" → FALSE (Makefile exists).
**True P0**: bot polling has NO watchdog — if `_poll_loop()` dies, nothing restarts it and
the bot silently stops serving subscribers. Agreed by belshe + b0rk.
**Action items**: P0 = bot watchdog (~S). P1 = consume booking_window_bucket (~S),
reconcile README to wired notifiers (~S), document generate_route_id hash contract (~S).
P2 = dynamic destinations, UserDealInteraction/classifier, /metrics, monetization, PG path.

## Latest Panel Re-Review (2026-07-16 23:30)

Re-audit of committed `eee3fbb` (5 lenses). **Verdict: APPROVED — correct, verified,
no regression.** All 5 panel scores unchanged (PMF 7, DX 7.5, Reliability 8, Moat 6,
Architecture 7). The 3 P1 backlog items from the UI review are still OPEN (see "What
a New Agent Needs" above). Pre-existing test warning at `price_analysis.py:139` is a
mock artifact, not a prod bug. Full entry in `docs/panel-decisions.md`
(2026-07-16 23:30).

## What a New Agent Needs to Know

**Working tree is CLEAN as of 2026-07-16 23:30**: all bug fixes, the Kayak
booking-link switch, UI/README relabel, new TDD tests, and re-review docs are
committed in `eee3fbb`. No uncommitted work.

**Open P1s (from 2026-07-16 re-review, NOT blockers)**:
1. `calculate_percentile_baseline()` does not filter by `booking_window_bucket`
   (price_analysis.py:234 scopes by `departure_month` only) — near-term deals can
   mis-score vs far-out baselines.
2. Booking-label is a literal string in 2 templates (not derived from the link
   host) — single-source-of-truth not yet done; guard test is interim only.
3. No Kayak link-health smoke test — would not catch a future Kayak deprecation
   (exactly what broke Google).

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

**Immediate (highest leverage)** — per 2026-07-16 full audit:
1. **P0: Add bot polling watchdog** — check `_poll_task.done()` in a periodic task and
   restart `_poll_loop()`; without this the bot silently dies (belshe/b0rk). ~S effort.
2. **P1: Consume `booking_window_bucket`** in `calculate_percentile_baseline()` — 1-line
   filter on `obs.booking_window_bucket`, improves detection accuracy (swyx/b0rk).
3. **P1: Reconcile README** — it claims Slack/Discord/email notifiers not all wired;
   state only Telegram + webhook notifiers actually exist (hanselman, B15).
4. **P1: Document `generate_route_id()` hash contract** — changing airline/suffix
   invalidates dedup silently; add code comment + test (b0rk).
Then (P2): dynamic DB-backed destinations `/watch` (levelsio), `UserDealInteraction`
model + false-positive classifier (swyx), `/metrics` (belshe), monetization (levelsio),
PostgreSQL multi-instance path (belshe).

> NOTE: Three prior "deferred bugs" were FALSE POSITIVES (verified 2026-07-16 against
> source): `_escape_md` double-escape, dead `elif` in scanner.py, and missing Makefile.
> Do NOT spend time "fixing" these — they are already correct/resolved.

## Live now (2026-07-16)

- Dev server running on **`:8787`** (`/dev/shm` SQLite). Login open → register at `/auth/register`.
- **Bug-fix + TDD sprint (2026-07-16)**:
  - **UI empty-data root cause — 2 bugs in `app/scrapers/fli_client.py`, FIXED**:
    1. fli returned `arrival_airport` as an `Airport` **enum**; `json.dumps()` in the subprocess crashed → every free search failed → fell through to paid providers (no keys) → zero deals. Added `_json_default()` (Enum→.value) + `from enum import Enum`; used in `json.dumps(default=...)`.
    2. `f"{result.price:.2f}"` raised `NoneType.__format__` when `price=None`, killing whole-route conversion. Guarded `price = result.price if result.price is not None else 0.0`; wrapped per-result `_to_dict()` in try/except so one bad result can't sink a route.
    - Result: `/deals` now returns 986 live deals (was 0). ruff clean.
  - **Booking link fix**: `_build_google_flights_url` (dead Google `?q=` format) replaced by `_build_booking_url` → **Kayak** path format `https://www.kayak.com/flights/MCI-JFK/2026-09-10` (RT appends `/return_date`). VERIFIED: Google deprecated **all** deep-link params in 2026 — every `q=`, path `/flights/MCI-JFK/...`, and hand-rolled `tfs=` variant 302s to `/unsupported` (the user's own example link now also 404s). Kayak path format returns 200 and pre-fills origin/dest/dates. Skyscanner path format hits captcha (unusable).
    - Backfilled all 986 existing `FlightDeal.booking_url` rows to Kayak via async script. Live `/deals` now serves `kayak.com/flights/...` links.
  - **TDD**: added 6 Kayak URL-builder tests (replacing 4 dead `?q=` tests) in `test_scheduler_jobs_extended.py`; added `TestFLIClientJsonDefault` + 3 `_to_dict` regression tests (enum arrival_airport, None price→0.00, zero price) in `test_fli_client.py`. 38 relevant tests pass; full suite 415 passed / 1 pre-existing fail (test_alembic — `alembic` not installed; opt-in).
- **Prior sprints still live**: reliability hardening, architecture extraction, learned baselines, Telegram bot, UI/UX QA fixes.

> NOTE: The 2026-07-15 deferred "open items" (bot `_escape_md` double-escape, scanner dead `elif`, Makefile) were verified FALSE POSITIVES by the 2026-07-16 panel re-review — do NOT "fix" them. Only `booking_window_bucket` consumption remains a real P1.

## Previous sprints (archived)

### Reliability sprint (2026-07-12)
Five hardening items: fli subprocess isolation, SECRET_KEY fail-fast, JobRun reconciliation, `/health` → 503, SQLite startup tolerance. All verified.

### One-way vs round-trip pricing (2026-07-11)
Tier 1 (trip_type discriminator + RT Google link) and Tier 2 (paid RT enrichment behind flag) both DONE. `round_trip_enrichment: true` enabled by default.
