# Flight Deal Monitor — Decision Log

All significant architectural decisions, feature trade-offs, and technical learnings
are logged here with datetime stamps. This is the source of truth for *why* things
are the way they are.

---

## 2026-07-12 14:00: Architecture Extraction (Rec 3)

**Decision**: Extracted `scheduler_jobs.py` (594L→175L) into 3 focused modules:
`app/job_lifecycle.py`, `app/alert_dispatch.py`, `app/scanner.py`.

**Rationale**:
- `scheduler_jobs.py` had 7 distinct responsibilities in one file (job lifecycle,
  stale reconciliation, sweep orchestration, route scanning, alert dispatch, URL
  building, fli timeout constant). This made it hard to test and reason about.
- Extraction order: job_lifecycle (lowest risk) → alert_dispatch → scanner (highest risk).
  Each step verified with full test suite before proceeding.

**Key constraint discovered**: Test files patch `app.scheduler_jobs.*` targets. Moving
functions to new modules requires updating patch paths in test files. We chose
**free-function form** (not classes) to minimize test changes — sweeps still call
`_scan_route()` and `_send_deal_alert()` as free functions, just imported from new
modules. See `tasks/lessons.md` entry "Test patch targets must move with extracted code".

**Reference**: `docs/plan-next-3.md` §3, `AGENTS.md` "Key functions" table.

---

## 2026-07-12 14:30: Learned Per-Route-Month Baselines (Rec 2)

**Decision**: Added `calculate_percentile_baseline()` using Python-side percentile
computation (sorted prices + index-based) instead of SQL `NTILE` or `PERCENTILE_CONT`.

**Rationale**:
- SQLite lacks `PERCENTILE_CONT` (Postgres-only). `NTILE(100)` was considered but
  rejected because it buckets *all* prices into exactly 100 groups — with <100 samples
  (common for new routes), NTILE produces coarse results. Python-side sorting + index
  interpolation gives exact percentiles regardless of sample count.
- The function returns a dict of `{P5, P10, P20, P30, P50}` prices so callers can
  choose their threshold without re-querying.
- `detect_deal_learned()` uses percentile thresholds (P20=mistake, P30=deep_flash,
  P50=flash_sale) when sufficient route+month data exists, falling back to the
  original median-based `detect_deal()` for cold-start routes.

**Reference**: `docs/plan-next-3.md` §2, `app/utils/price_analysis.py:calculate_percentile_baseline`.

---

## 2026-07-12 15:00: Interactive Telegram Bot (Rec 1)

**Decision**: Built `BotHandler` in `app/bot.py` using raw `httpx` long-polling
(`getUpdates` with 30s timeout) instead of `python-telegram-bot` library.

**Rationale**:
- `python-telegram-bot` v21 is ~500KB with its own event loop management that
  conflicts with the existing asyncio + APScheduler setup.
- We only need `getUpdates` (polling) + `sendMessage` — both are simple HTTP calls.
- FastAPI lifespan runs the polling loop as a background task alongside the scheduler.
- Zero risk of event loop conflicts.

**Key design choices**:
- `TelegramSubscription` SQLModel stores per-user filters (origin/destination).
- `send_alert_to_subscribers()` fans out to all active subscribers, filtering by
  route. Falls back to legacy hardcoded `chat_id` when no subscribers exist.
- Bot polling is best-effort: failure to start doesn't block app boot.

**Reference**: `docs/plan-next-3.md` §1, `app/bot.py`, `app/models/telegram.py`.

---

## 2026-07-12 15:30: Documentation & Automation Infrastructure

**Decision**: Created `docs/MEMORY.md` (this file), `tasks/lessons.md`, and
`scripts/run_tests.sh` (idempotent test runner).

**Rationale**:
- Previous sessions had no persistent decision log — each session started from
  scratch. MEMORY.md captures *why* decisions were made so future sessions (and
  humans) can understand the context.
- `tasks/lessons.md` captures failure modes and prevention rules (per AGENTS.md §4).
- `scripts/run_tests.sh` is an idempotent script that handles DATABASE_URL setup,
  PYTHONPATH, and test selection so anyone can run tests without remembering the
  exact incantation.

**Reference**: `AGENTS.md` "Learning & Decision Logging" section.
