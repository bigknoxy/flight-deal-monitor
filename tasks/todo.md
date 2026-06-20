# Flight Deal Monitor - Test Coverage 85%+

## Current State
- 19 tests, 44% coverage
- 885 total statements, 499 uncovered

## Target
- 85%+ statement coverage
- Meaningful tests only (catch real bugs or validate critical behavior)
- CI enforcement on PRs

## Priority Plan (highest business value first)

### Phase 1: Pure logic / no DB needed (quick wins)
- [x] `app/alert.py` - `_format_alert_message`, `_is_rate_limited` 
- [x] `app/cache.py` - `TTLCache` TTL expiry, boundary conditions
- [x] `app/api/searchapi.py` - `_normalize_flight`, `get_flight_price`
- [x] `app/utils/price_analysis.py` - `calculate_median_price` edge cases, `calculate_price_drop` zero median

### Phase 2: API endpoints / scheduler
- [x] `app/main.py` - root, health, config endpoints (FastAPI test client)
- [x] `app/scheduler.py` - start, shutdown, get_scheduler_status
- [x] `app/alert.py` - `send_alert`, `test_connection` with mocked HTTP
- [x] `app/config.py` - YAML loading, env validation

### Phase 3: Integration-heavy
- [x] `app/scheduler_jobs.py` - `_start_job_run`, `_complete_job_run`, `_fail_job_run`
- [x] `app/database.py` - init_db, close_db
- [x] `app/scheduler_jobs.py` - `_scan_route` fallback chains

### Phase 4: CI Enforcement
- [x] Add coverage configuration to pyproject.toml
- [x] Add coverage enforcement to CI

## Verification
- [ ] Run full test suite with coverage
- [ ] Report final coverage %
- [ ] Confirm CI enforcement is in place
