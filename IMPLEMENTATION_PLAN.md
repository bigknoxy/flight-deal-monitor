# Flight Deal Monitor - Comprehensive Implementation Plan

## Research Summary: Similar GitHub Repos

### Repos Analyzed
1. **sergiomoita/flight-bot** - RSS-based approach, daily Telegram digest, SQLite persistence
   - Takeaway: Good for RSS feed monitoring (future enhancement)
   - Pattern: Daily digest vs real-time alerts

2. **vasadasa0304-sudo/flight-fare-monitor** - PostgreSQL + Streamlit UI, YAML-driven routes
   - Takeaway: Streamlit UI is simple and effective for route management
   - Pattern: Relational schema with routes, search_configs, fare_snapshots
   - Pattern: Cache TTL optimization (600s to reduce DB round trips)

3. **DebanilBora/flight-deals** - SMS/Email alerts via Twilio, Google Sheets integration
   - Takeaway: Multi-channel alerts (SMS + Email + Telegram) improve reliability
   - Pattern: Sheety for Google Sheets (good for manual review)

---

## Phase 1: Quick Wins (This Week)
**Priority**: High | **Effort**: Low-Medium | **Timeline**: 1-2 days

### 1.1 Add `.env.example` Template
**Status**: ✅ Blocked
- Create `config/.env.example` with all required env vars
- Document each variable in comments
- Include default/safe values where appropriate
**File**: `config/.env.example`

### 1.2 Extract Real Booking URLs from API Responses
**Status**: ✅ Blocked
- Fix line 218 in `app/scheduler_jobs.py` (hardcoded example.com)
- Add `booking_url` extraction method to both Amadeus and Duffel clients
- Handle cases where booking URL might not be available
**Files**: `app/api/amadeus.py`, `app/api/duffel.py`, `app/scheduler_jobs.py`

### 1.3 Add Alert History API Endpoint
**Status**: ✅ Blocked
- Add `GET /alerts/history` endpoint with pagination
- Add query parameters: `?start_date=&end_date=&deal_type=&limit=`
- Add `GET /alerts/{alert_id}` endpoint for individual alerts
**Files**: `app/main.py`

### 1.4 Add Structured Logging (JSON format)
**Status**: ✅ Blocked
- Replace default logging with structlog or python-json-logger
- Add correlation IDs to track request flow
- Format logs for log aggregation (ELK, Grafana Loki, etc.)
**Files**: `app/main.py`, `app/config.py`, `requirements.txt`

### 1.5 Add Prometheus Metrics Endpoint
**Status**: ✅ Blocked
- Add `GET /metrics` endpoint with Prometheus metrics
- Track: API calls per provider, alerts sent, deals detected, job durations, error rates
- Use prometheus-client library
**Files**: `app/main.py`, `app/metrics.py` (new), `requirements.txt`

### 1.6 Add API Health Checks for External APIs
**Status**: ✅ Blocked
- Add `GET /health/apis` endpoint
- Check Amadeus and Duffel API connectivity
- Return status for each API provider
**Files**: `app/main.py`, `app/api/amadeus.py`, `app/api/duffel.py`

---

## Phase 2: Core Enhancements (Next Sprint)
**Priority**: High | **Effort**: Medium-High | **Timeline**: 3-5 days

### 2.1 Simple Web UI for Route Management
**Status**: ⬜ Planned
- Use Streamlit (inspired by vasadasa0304-sudo/flight-fare-monitor)
- Pages: Dashboard (active deals), Routes (manage home_airports/destinations), Alerts (history), Settings
- Update `config/app.yaml` via UI
**Files**: `app/ui/` (new), `requirements.txt`

### 2.2 Email Alerts (Telegram Backup)
**Status**: ⬜ Planned
- Add SMTP configuration to `.env`
- Implement email alerting class similar to `TelegramBot`
- Fallback: If Telegram fails, send email
- Use SendGrid or AWS SES for production
**Files**: `app/alert.py`, `config/app.yaml`, `config/.env.example`

### 2.3 Historical Deal Analytics
**Status**: ⬜ Planned
- Add aggregation queries for deal statistics
- Endpoints:
  - `GET /analytics/deals-by-route` - Most common deal routes
  - `GET /analytics/deals-over-time` - Deal frequency over time
  - `GET /analytics/price-drops` - Distribution of price drops
- Add to Web UI with charts (Plotly)
**Files**: `app/analytics.py` (new), `app/main.py`

### 2.4 Redis Integration for Caching
**Status**: ⬜ Planned
- Add Redis for:
  - API response caching (flight search results)
  - Rate limiting (token bucket algorithm)
  - Session management (for Web UI)
- Configure via `.env`
**Files**: `app/cache.py` (new), `requirements.txt`, `docker-compose.yml`

### 2.5 Database Migrations with Alembic
**Status**: ⬜ Planned
- Initialize Alembic for database migrations
- Create initial migration from current schema
- Add migration for any new Phase 2 tables
**Files**: `migrations/` (new), `alembic.ini`, `requirements.txt`

---

## Phase 3: Production Readiness (Later)
**Priority**: Medium | **Effort**: High | **Timeline**: 1-2 weeks

### 3.1 PostgreSQL Migration
**Status**: ⬜ Planned
- Migrate from SQLite to PostgreSQL
- Update `DATABASE_URL` in `.env`
- Add connection pooling (SQLAlchemy pool)
- Update CI/CD for PostgreSQL support
**Files**: `docker-compose.yml`, `app/database.py`, `.github/workflows/ci-cd.yml`

### 3.2 User Authentication
**Status**: ⬜ Planned
- Add JWT-based authentication for Web UI
- Users: admin (full access), read-only (view-only)
- Protect routes with `@require_auth` decorator
**Files**: `app/auth.py` (new), `app/main.py`

### 3.3 Enhanced Observability
**Status**: ⬜ Planned
- Add distributed tracing (OpenTelemetry)
- Add structured error reporting (Sentry)
- Add uptime monitoring (Pingdom/Statuspage integration)
- Add log aggregation (Grafana Loki or CloudWatch)
**Files**: `app/observability.py` (new), `requirements.txt`

### 3.4 Security Enhancements
**Status**: ⬜ Planned
- Add API key validation on startup
- Add input validation with Pydantic
- Add rate limiting on public endpoints
- Add security scanning (Bandit) to CI/CD
- Add dependency vulnerability scanning (Snyk/Trivy)
**Files**: `app/security.py` (new), `.github/workflows/ci-cd.yml`

### 3.5 API Resilience Patterns
**Status**: ⬜ Planned
- Add retry logic with exponential backoff (tenacity)
- Add circuit breakers for API failures (circuitbreaker)
- Add request/response deduplication
- Add API health monitoring with auto-failover
**Files**: `app/api/amadeus.py`, `app/api/duffel.py`, `requirements.txt`

### 3.6 Multi-channel Alerts
**Status**: ⬜ Planned
- Add SMS alerts (Twilio) as tertiary channel
- Add Discord webhook support
- Configurable alert channels per user
- Alert escalation (Telegram → Email → SMS)
**Files**: `app/alert.py`, `config/app.yaml`

---

## Implementation Strategy

### Kanban Board Structure
- **Backlog**: All Phase 1-3 tasks
- **Ready**: Tasks ready to start (dependencies met)
- **In Progress**: Currently being worked on by subagents
- **Code Review**: Ready for review
- **Testing**: Undergoing integration testing
- **Done**: Completed and merged to main

### Subagent Roles
- **Orchestrator**: Coordinates overall workflow, manages kanban board
- **Researcher**: Analyzes similar repos, documents patterns
- **Coder**: Implements features, writes code
- **Reviewer**: Code review, testing, quality checks

### Branching Strategy
- `main` - Production branch
- `develop` - Integration branch
- `feature/*` - Feature branches (one per task/phase)
- `bugfix/*` - Bug fixes

### CI/CD Flow
1. Push to `feature/*` → Run tests + lint
2. Open PR → Reviewer subagent checks
3. Merge to `develop` → Integration tests
4. Merge to `main` → Build Docker image → Deploy

---

## Success Criteria

### Phase 1 Success
- ✅ `.env.example` exists and is documented
- ✅ Booking URLs extracted from APIs
- ✅ Alert history endpoint working
- ✅ Structured logging in place
- ✅ Prometheus metrics exported
- ✅ API health checks operational

### Phase 2 Success
- ✅ Web UI accessible for route management
- ✅ Email alerts working as backup
- ✅ Historical analytics data available
- ✅ Redis caching reducing API calls
- ✅ Database migrations set up

### Phase 3 Success
- ✅ PostgreSQL operational
- ✅ User authentication working
- ✅ Observability stack integrated
- ✅ Security scanning in CI/CD
- ✅ API resilience patterns implemented
- ✅ Multi-channel alerts functional

---

## Next Steps
1. Set up kanban board with all tasks
2. Start Phase 1 with `.env.example` task
3. Deploy subagents to work in parallel on independent tasks
4. Review and merge as tasks complete
5. Move to Phase 2 once Phase 1 is complete