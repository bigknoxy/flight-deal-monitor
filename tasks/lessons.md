# Lessons Learned

Failure modes, detection signals, and prevention rules captured during development.
Review at session start and before major refactors.

---

## Lesson 1: Test patch targets must move with extracted code

**Failure mode**: Extracting functions from `scheduler_jobs.py` to new modules broke
all test patches that targeted `app.scheduler_jobs.*` — Python resolves a function's
free variables using the *defining module's* `__globals__`, so patches at the old
module path no longer affect the moved code.

**Detection signal**: Tests pass before extraction, fail after with "patch target not
found" or "function not patched" errors.

**Prevention rule**: When extracting code to a new module, grep for ALL patch targets
and import references across the test suite FIRST. Update them in the same commit as
the extraction. Use `grep -rn "app\.scheduler_jobs\._" tests/` as a checklist.

**Reference**: `docs/plan-next-3.md` §3, `docs/MEMORY.md` "Architecture Extraction".

---

## Lesson 2: Free functions over classes for mechanical extraction

**Failure mode**: Wrapping extracted functions in classes (`ScannerService`,
`AlertDispatcher`) requires rewriting call sites from `_scan_route(session, ...)`
to `ScannerService(session).scan_route(...)`, which breaks test patches and
increases diff scope.

**Detection signal**: Plan says "extract to class" but tests patch the free function.

**Prevention rule**: For pure mechanical extraction (no behavior change), keep
module-level free functions. Only introduce classes when the extraction adds new
behavior (state, lifecycle, dependency injection).

**Reference**: `docs/MEMORY.md` "Architecture Extraction — Key constraint discovered".

---

## Lesson 3: SQLite NTILE is coarse for small sample sizes

**Failure mode**: Using `NTILE(100)` on a table with <100 rows produces buckets
with 0-1 rows, making percentile queries unreliable for new routes.

**Detection signal**: Learned baseline returns P25 = P50 because NTILE can't
distinguish with <100 samples.

**Prevention rule**: Use Python-side sorted-price + index-based percentile
computation instead of SQL NTILE. This gives exact percentiles regardless of
sample count. Only switch to SQL `PERCENTILE_CONT` when migrating to Postgres.

**Reference**: `docs/MEMORY.md` "Learned Per-Route-Month Baselines".

---

## Lesson 4: Bot polling must not block app boot

**Failure mode**: If Telegram bot token is missing or invalid, the polling loop
should not crash the app or prevent the scheduler from starting.

**Detection signal**: App fails to boot with Telegram connection error.

**Prevention rule**: Gate bot polling behind `config.env.telegram_bot_token` being
non-empty. Wrap `start_polling()` in try/except with a warning log. The bot is a
best-effort feature, not a boot dependency.

**Reference**: `docs/MEMORY.md` "Interactive Telegram Bot", `app/main.py` lifespan.
