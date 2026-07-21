# Handoff — flight-deal-monitor

> **This document must always be current. Do not leave stale. Update it
> whenever a significant change is made or a panel decision is recorded.**

## Last Updated
2026-07-21 (panel review of PR #16 notifier-status banner + dedup rollback; app avg **8.0/10 flat** vs 2026-07-19(2) baseline; PR #16 green CI, OPEN — awaiting user merge)

## Current Status

| Area | Status |
|---|---|
| Tests | 494 passing, 8 skipped (+9 from PR #16: 6 config + 2 dashboard + 1 dedup) |
| Coverage | 85.81% (gate 85.0%) |
| Lint | `ruff check app/ tests/` clean (exit 0) |
| CI | Green on PR #16 (lint pass 11s, test pass 54s, build skipped — PR not on main) |
| Open PRs | **#16** — `fix/notifier-status-banner-and-dedup-rollback` @ `ca14b3c` (awaiting user merge) |
| Open Issues | None — all prior P1s + bot-watchdog P0 CLOSED in code |
| AGENTS.md | Updated |
| Panel system | Specialized agents in `.opencode/agents/*.md` (no model pin → default poolside/laguna-m.1); `opencode.json` gpt-4o override removed 2026-07-19. Task-tool `subagent_type` enum uses a separate built-in (gpt-4o) — use opencode native agent runtime, not the Task tool |
| Git state | PR #16 branch pushed; working tree has uncommitted `.gstack/` QA report (gitignored) |

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
| 2 | `ca14b3c` | fix(notifier+dedup): unconfigured-alerts banner + dedup cleanup rollback safety (PR #16, green CI) |

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

**Immediate (highest leverage)** — per 2026-07-21 panel review of PR #16
(all P2, non-blocking; PR itself is APPROVED and ready to merge):

1. **Merge PR #16** — `gh pr merge 16 --squash --delete-branch` after user signal.
   Green CI verified: lint pass (11s), test pass (54s), build skipped (PR not on main).
2. **README sync (P2, XS)** with banner behavior — repo rule: README must mention
   that the dashboard shows a warning when no alert channels are configured.
3. **Partial-config distinction (P2, S, b0rk)** — `Config.notifier_status()` v2
   distinguishes `partially_configured` (e.g., telegram token but no chat_id) from
   `none`. Current behavior shows "no channels configured" for partial configs,
   which feels wrong to the user.
4. **HTMX-live banner hide (P2, S, hanselman)** — configuring a notifier from
   /settings should hide the warning banner without requiring a full reload; align
   with the dashboard's existing HTMX reactivity.
5. **Send-test-alert button (P2, M, levelsio)** on /settings — closes the
   misconfigured-notifier failure mode that existence-checks can't catch (expired
   token, wrong chat_id, bounced email).
6. **Detection-health banner (P2, M, swyx)** — extend this banner pattern to
   "Last successful scan: 3h ago" / "MCI→LHR 0 deals in 7 days — route may be stale."
   First concrete step toward the data-loop closure swyx flagged in prior panels.

**Carried-forward backlog (still open from prior panels):**
- B8 `/metrics` endpoint (belshe, M) — observability for anomaly alerting
- B15 README full reconc (hanselman, S) — includes the P2 README sync above
- B17-B25 `UserDealInteraction` + `booking_window_bucket` consumption (swyx, M-L)
- WAL/backup for job-store SQLite (belshe, M)
- fli scraper brittleness mitigation (b0rk, M) — biggest cross-cutting risk
- MCI hardcoded → config (levelsio, S) — multi-origin / multi-user potential

**Scope reminder**: monetization / multi-user DB migration is **OUT OF SCOPE**
(personal/family tool). Do not act on prior panel mentions of multi-tenant Postgres.

> NOTE: Three prior "deferred bugs" verified FALSE POSITIVES on 2026-07-16
> (`_escape_md` double-escape, dead `elif` in scanner.py, missing Makefile).
> Do NOT spend time "fixing" these — they are already correct/resolved.

## Previous sprints (archived)

### Reliability sprint (2026-07-12)
Five hardening items: fli subprocess isolation, SECRET_KEY fail-fast, JobRun reconciliation, `/health` → 503, SQLite startup tolerance. All verified.

### One-way vs round-trip pricing (2026-07-11)
Tier 1 (trip_type discriminator + RT Google link) and Tier 2 (paid RT enrichment behind flag) both DONE. `round_trip_enrichment: true` enabled by default.
