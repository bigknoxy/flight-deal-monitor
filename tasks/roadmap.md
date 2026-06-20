# Flight Deal Monitor - Development Plan

## CEO Review — Strategic Foundation

### Premises
1. Flight deal monitoring is valuable for cost savings on travel
2. Users want both targeted alerts and serendipitous deal discovery
3. Free flight data sources are blocked or expensive
4. The system should be fully hands-off after initial setup

### Problem Statement
Build a flight deal monitoring system that finds real deals for MCI-based travelers to LHR and other destinations, sending Telegram alerts when prices drop significantly below historical medians.

### Current State
- `fli` library IS working (returns real data) - FREE option available
- SearchAPI is $4/1K as fallback
- 19 tests passing

### Alternatives Considered
1. **Free only** (browser automation) - requires network to google.com
2. **fli library** - tested and working, FREE
3. **SearchAPI** - $4/1K, reliable fallback

### Selected Approach
Use `fli` library as primary (free), SearchAPI as backup.

---

## Design Review — UX Considerations

**UI Scope: None** - This is a backend service with Telegram alerts

**Interaction Model:**
- Setup: Configure airports, destinations in YAML
- Runtime: System polls, sends Telegram messages
- No user interface needed

---

## Engineering Review — Architecture

### File Structure
```
app/
├── scrapers/
│   ├── fli_client.py    # Primary - FREE
│   └── __init__.py
├── api/
│   └── searchapi.py     # $4/1K fallback
├── scheduler_jobs.py    # Job orchestration
├── alert.py             # Telegram
└── config.py            # Settings

config/
├── app.yaml             # Airports, destinations
└── .env.example         # API keys
```

### Key Decisions
- Use `fli` library (tested working)
- Cache 6-hour TTL
- Telegram alerts for deals

---

## Product Goals

1. **Targeted Alerts**: MCI → LHR deals
2. **General Discovery**: Best deals across configured destinations
3. **Hands-off**: Configure once, run forever
4. **Cost-effective**: Prefer free sources

---

## Implementation Roadmap

### Phase 1: Core Monitoring ✅
- [x] fli client working
- [x] SearchAPI fallback configured
- [x] Tests passing

### Phase 2: Deal Detection
- [ ] Test fli integration in scheduler
- [ ] Verify deal detection logic
- [ ] Test Telegram alerts

### Phase 3: General Discovery
- [ ] Multi-destination scanning
- [ ] Configurable look-ahead days
- [ ] Price history tracking

### Phase 4: Production Ready
- [ ] Health checks
- [ ] Logging/metrics
- [ ] Docker deployment

---

## Questions for User

1. **Home airports**: Currently MCI, LAX, JFK - keep or change?
2. **Destinations**: LHR, CDG, NRT, DXB, SYD - good list?
3. **Deal thresholds**: 40% flash sale, 30% mistake fare - right values?
4. **Frequency**: Every 30min regular, 15min for mistake fares - good?

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | /autoplan | Strategy & scope | — | pending | — |
| Design Review | /autoplan | UI/UX gaps | — | pending | — |
| Eng Review | /autoplan | Architecture & tests | — | pending | — |
| DX Review | /autoplan | Developer experience | — | pending | — |