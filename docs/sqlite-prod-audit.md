# SQLite Production Safety Audit

## Verified-Shipped Items (with evidence)

| Feature | Evidence |
|---------|----------|
| WAL mode + busy_timeout + synchronous=NORMAL | `app/database.py:44-46` - PRAGMA settings in `set_sqlite_pragma` event listener |
| Circuit breaker for paid API tiers | `app/utils/circuit_breaker.py:8-72` - `CircuitBreaker` class with `is_allowed()`, `record_success/failure()` |
| Orphaned JobRun reconciliation | `app/job_lifecycle.py:25-55` - `reconcile_stale_job_runs()` called at startup in `app/main.py:83` |
| Dedup retry logic | `app/utils/deduplication.py:41-100` - `is_flight_seen_recently()` checks AlertHistory failures, retries up to `MAX_ALERT_ATTEMPTS=5` |

## Remaining Production-Safety Gaps (ranked by risk)

### 1. Scheduler job store shares same SQLite file as app DB (HIGH RISK)
- **Location**: `app/scheduler.py:23`
- **Issue**: `SQLAlchemyJobStore(url=config.env.database_url)` uses the same database file as the app's `AsyncSessionLocal`. During sweeps, both the scheduler (writing job metadata) and app (reading/writing deals) compete for the same SQLite file.
- **Risk**: SQLite locks the entire database file during writes. With 19 destinations × weekly checks + mistake sweeps, concurrent access can cause `database is locked` errors, especially under load.
- **Fix**: Separate the job store to a different SQLite file (e.g., `flight_deals_jobs.db`) or add explicit connection pooling with timeout.

### 2. Bare `sqlite://` URL footgun (RE-CHECKED — NOT A REAL RISK)
- **Location**: `app/utils/database_url.py:14-23`
- **Re-checked**: `get_async_database_url` raises a clear `ValueError("Unsupported
  database scheme: ")` for empty/invalid schemes, and tests in
  `tests/test_database_url.py` cover empty-string + unsupported-scheme error paths.
  The prior "footgun" claim was incorrect — the code is robust. No fix needed.
- **Note**: `AGENTS.md` still warns that bare `sqlite://` fails for the *job store*
  without a trailing path; that guidance is about trailing-slash formatting, not a
  crash on empty — reword if desired.

### 3. No backup/WAL checkpointing strategy (MEDIUM RISK)
- **Location**: No code found
- **Issue**: No periodic WAL checkpointing or backup mechanism. For a personal deployment, a corrupted SQLite file means data loss.
- **Risk**: WAL grows unbounded; no way to recover from corruption or accidental deletion.
- **Fix**: Add periodic WAL checkpoint (e.g., on startup/shutdown) and document backup procedure.

### 4. Shutdown race with in-flight jobs (LOW RISK)
- **Location**: `app/main.py:116-117`
- **Issue**: `shutdown_scheduler()` uses `wait=True` but doesn't coordinate with in-flight sweep jobs that may still be using the DB.
- **Risk**: Jobs terminated mid-write could leave partial data; watchdog task cancellation may race with DB access.
- **Fix**: Add explicit job quiescence before scheduler shutdown.

## Status (2026-07-19)

### FIXED: Gap #1 — scheduler job store separated (commit cc16c32-era follow-up)
- `app/config.py` added `scheduler_jobstore_url: str = "sqlite:///./data/flight_deals_jobs.db"`
  (env override `SCHEDULER_JOBSTORE_URL`).
- `app/scheduler.py:39-44` now builds `SQLAlchemyJobStore(url=config.env.scheduler_jobstore_url,
  engine_options={"connect_args": {"timeout": 5}})`; `_ensure_jobstore_dir()` creates the
  directory at import. Job-metadata writes no longer contend with app deal-data writes.
- `tests/test_scheduler_jobstore.py` (6 tests) asserts the separation + dir creation + timeout.
- Full suite: 485 passed / 8 skipped, ruff clean.

### DEFERRED (acceptable for single self-host)
- **WAL on the job-store file**: not applied (job store has trivial, infrequent write volume;
  app DB keeps WAL). `timeout=5` (busy_timeout) gives adequate lock protection. Revisit only
  if job-store contention is ever observed.
- **Gap #3 (backup/WAL checkpoint) + Gap #4 (shutdown quiescence)**: both LOW/MEDIUM and out
  of scope for a personal/family deployment. Document a manual `cp flight_deals.db*` backup as
  the recovery path for now.

### Conclusion
For a single self-hosted instance (owner + family), the meaningful production-safety gap was
the shared SQLite file. That is now closed. Remaining items are low-risk and deferred.
Monetization / multi-user DB migration remains explicitly OUT OF SCOPE per user decision.
