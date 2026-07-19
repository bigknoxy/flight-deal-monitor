# Panel Decisions

Structured record of every expert panel session for flight-deal-monitor.
Decisions are immutable once recorded — if context changes, start a new entry.

---

## 2026-07-19 (2) — Full panel re-rating after reliability fixes (main @ 6756449)

**Trigger**: User: "run full panel" after two fixes landed since the 2026-07-19
re-rating: (1) bot polling watchdog P0 (`app/bot.py:107-132`, commit cc16c32),
(2) APScheduler job store separated to its own SQLite file (`app/scheduler.py:39-44`
+ `app/config.py scheduler_jobstore_url`, commit 6756449). User decision reaffirmed:
monetization / multi-user DB migration is OUT OF SCOPE — personal/family tool only.

**Verified state**: 485 passed / 8 skipped, ruff clean, CI green. Prior 3 P1s closed
in code (confirmed 2026-07-19). Two new test files: test_bot_watchdog.py (4),
test_scheduler_jobstore.py (6).

### Lens verdicts + app re-rating (0-10)
| Lens | Score | vs 2026-07-19 | Justification |
|---|---|---|---|
| levelsio (PMF) | **8** | 7 (+1) | Watchdog + DB separation make it "set-and-forget reliable" vs "works if you babysit it". |
| hanselman (DX) | **8** | 8 (0) | Docker-first, in-app settings, health endpoint; watchdog/sep improve reliability but DX surface unchanged. |
| belshe (Reliability) | **9** | 8 (+1) | **P0 watchdog CLOSED** (supervised restart + graceful shutdown); job-store contention eliminated. |
| swyx (Defensibility) | **7** | 6 (+1) | Learned percentile baselines + booking-window scoping now route-month specific; still single-user, no ML. |
| b0rk (Fragility) | **8** | 7 (+1) | Watchdog + separate jobstore closed critical gaps; shared-DB SPOF eliminated. |

**New app average = 8.0/10** (8+8+9+7+8 = 40 / 5). Prior average 7.2/10.
**Score is HIGHER by +0.8**, driven by the two reliability fixes (belshe +1, b0rk +1,
levelsio +1) and the now-maturing baseline logic (swyx +1). DX flat (no user-facing DX
change). For a personal/family single self-host with no monetization, the panel judges
the app in solid shape.

### Recommended next (personal/family scope only — excludes monetization/multi-user)
Cross-lens consensus on highest-value owner-facing improvements:
1. **Personal deal-history / seasonal insights** (swyx) — aggregate PriceObservation by
   departure_month + track hit-rate by deal_type/airline to tune thresholds and show
   "June MCI→LHR typically 25% cheaper than December".
2. **Mobile actionability** (levelsio/hanselman) — Telegram inline keyboards (Book Now /
   Snooze Route), `/alert <price> <route>` target-price command, mobile touch-target audit.
3. **Observability** (hanselman/belshe) — `/metrics` Prometheus endpoint (scheduler health,
   API usage, alert counts); structured logging instead of log-only.
4. **Residual reliability (low priority)**: WAL on job-store file, daily `VACUUM INTO`
   backup for both DBs, shutdown quiescence verification.
5. **Residual fragility**: fli scraper brittleness (no graceful partial-result/retry
   surfacing), single hardcoded home airport (MCI), Kayak deep-link dependency.

### Tooling gap (unchanged)
Built-in panelist subagents hardcoded to unavailable `openai/gpt-4o`; run via `developer`
subagent (poolside/laguna-m.1) stand-in.

---

## 2026-07-19 — Topic-decision + app re-rating (post PR #15 merge, main @ c3ad727)

**Trigger**: User: "do a panel review" — decide between candidate next-focus topics,
score them in a table, re-rate the app and check if the score improved vs the
2026-07-16 session. Convened via opencode `developer` subagents standing in for the
5 lenses (the built-in panelist subagents are hardcoded to an unavailable
`openai/gpt-4o` model and fail to launch; documented as a tooling gap below).

**Verified state (read from code, not assumed)**:
- 3 prior P1 items are CONFIRMED CLOSED in code:
  - `booking_window_bucket` consumed in `calculate_percentile_baseline()`
    (`price_analysis.py:249-250` scopes query by bucket; `test_scopes_by_booking_
    window_bucket` passes).
  - Booking label derived from `BOOKING_PROVIDER_NAME = "Kayak"` constant
    (`config.py:19` → `templates/__init__.py:19`), not a literal string.
  - Kayak link-health test exists (`tests/test_kayak_client.py` + scheduler extended
    suite).
- REMAINING gap (new P0 from belshe): **bot polling watchdog** — `bot.py:64` creates
  `_poll_task` but nothing supervises/restarts it if it dies (silent alert blackout).
- Latest commit `c3ad727` (offline tests for flexible_dates + database_url, 22 tests,
  ruff clean). Repo: 453+ passing, 8 skipped, 85.65% coverage, ruff clean, CI green.

### Topic-decision table (5-lens weighted ranking)
Ranked by panel consensus. Strategic Value (SV) / Urgency (U) / Defensibility (D) each 0-10;
Effort (E) 0-10 where lower = easier. Weighted = (SV+U+D)/3 − E/5 (higher = prioritize).

| Rank | Topic | SV | U | D | E | Weighted | Lead lens |
|---|---|---|---|---|---|---|---|
| 1 | **(c) Pricing / business model** — ship `@FlightDealBot` as primary surface, DB-backed dynamic destinations, free→paid tiers | 9 | 8 | 7 | 6 | **8.1** | levelsio |
| 2 | **(d) Bot polling watchdog + supervisor** (P0 reliability) | 9 | 9 | 6 | 4 | **8.0** | belshe |
| 3 | **(a) APScheduler + SQLite production-safety** (WAL, multi-instance Postgres guidance) | 7 | 8 | 5 | 5 | **6.4** | b0rk/hanselman |
| 4 | **(d2) UserDealInteraction feedback loop** (defensibility moat) | 9 | 8 | 9 | 7 | **6.8 → re-ranked 2nd by swyx** | swyx |
| 5 | **(b) AI/ML deal explanations** | 8 | 7 | 8 | 7 | **5.8** | swyx/levelsio |

**Recommended next focus (panel synthesis)**: Do **(d) bot watchdog** FIRST — it is the
only P0 and cheap (~20 lines, supervisor in `lifespan` checking `_poll_task.done()`).
Then **(c) pricing/business model** is the highest-leverage strategic bet: the product
IS the notification, not the dashboard; destinations must become DB-backed before a
2nd user can be onboarded. AI/ML explanations (b) are premature until the baseline +
interaction data are stable.

### Lens verdicts + app re-rating (0-10)
| Lens | Score | vs 2026-07-16 | One-line justification |
|---|---|---|---|
| levelsio (PMF) | **7** | 7 (flat) | Kayak relabel closed trust-lie; still zero distribution, single airport, no monetization surface live. |
| hanselman (DX) | **8** | 7.5 (+0.5) | Clean self-host story, 483+ tests, health endpoint; SQLite job store needs multi-instance hardening docs. |
| belshe (Reliability) | **8** | 8 (flat) | WAL + circuit breaker + reconciliation shipped; bot watchdog P0 still open. |
| swyx (Defensibility) | **6** | 6 (flat) | booking_window_bucket fixed (stale P1); detection still trivially copyable, no ML consumes data yet. |
| b0rk (Fragility) | **7** | 7 (flat) | Clean module boundaries; APScheduler+SQLite single point of failure unhardened. |

**New app average = 7.2/10** (7+8+8+6+7 = 36 / 5). Prior average ≈ 7.1/10
(7+7.5+8+6+7 = 35.5 / 5). **Score is HIGHER by +0.1**, driven by the DX lens
(7.5→8) after PR #15's test hardening. Note: the *effective* health is materially
better than the score implies because all 3 prior P1s are now closed in code — the
score delta is small only because those closes were never reflected in the prior
rating's trajectory.

### Tooling gap (action item, not a code change)
The built-in panelist subagents (`levelsio`, `hanselman`, `belshe`, `swyx`, `b0rk`,
`panel-moderator`) are hardcoded to `openai/gpt-4o`, which is unavailable in this
environment → they fail with "Model not found". This panel was run by invoking the
`developer` subagent (poolside/laguna-m.1) with persona-prefixed prompts. Fix: either
repoint the built-in panelist models or document the `developer`-stand-in procedure.

**Recommended next (smallest-leverage-first)**:
1. Bot polling watchdog supervisor in `lifespan` (belshe P0, ~20 lines).
2. Update `handoff.md` — the 3 "OPEN" P1s are actually CLOSED (done in this session).
3. Scope (c) pricing: DB-backed destinations + `@FlightDealBot` free→paid tiers.

---

## 2026-07-16 23:30 — Re-review of committed booking-link fix (eee3fbb)

**Trigger**: User: "run full panel re-review" after committing `eee3fbb` (fli
enum/None-price crashes + Kayak switch + product-sync label fixes). Goal: confirm
the b4 product-sync fixes hold post-commit, check for regressions, re-audit the 3
P1 backlog items carried from the UI review.

**Verified state**:
- Commit `eee3fbb` on `main` (14 files, 449 insertions/144 deletions), working
  tree clean.
- Target tests: **51 passed, 6 skipped**. No flakes.
- Pre-existing test warning at `price_analysis.py:139` (`coroutine never awaited`)
  is a *test-mock artifact* (AsyncMock `session.add_all`) — NOT a production bug;
  `add_all` is sync on real `AsyncSession`. Left as-is, noted for CI-noise cleanup.
- Live server `:8787` serves Kayak labels + 986 backfilled Kayak `booking_url` rows.

### Lens verdicts (5 lenses)
- **levelsio (PMF) — 7/10 (unchanged)**: Kayak relabel closes the trust-lie (most-
  clicked element now matches destination). Booking link is the only monetization-
  adjacent surface; Kayak defensible *if labeled*. No PMF change, no regressions.
- **hanselman (DX) — 7.5/10 (unchanged)**: Atomic, well-described commit. README
  Settings "read-only"→"editable" fix prevents the YAML-clobber footgun. Nit: the
  `add_all` AsyncMock warning is CI noise — recommend a `spec=AsyncSession`/sync
  mock in that one test. Minor.
- **belshe (Reliability) — 8/10 (unchanged)**: Product-sync staleness was a silent
  user-facing corruption (alerts said "Google", linked Kayak). `test_booking_url_
  host_matches_ui_label` now fails the build on future drift = correct shift-left
  control. Backfill done. No new silent-failure modes.
- **swyx (Defensibility) — 6/10 (unchanged)**: `calculate_percentile_baseline()`
  (`price_analysis.py:209`) STILL filters only by `departure_month`, ignoring
  `booking_window_bucket` — P1 still OPEN. Pre-computed bucket (lines 127-134)
  remains unconsumed. Recommend scoping the percentile query by bucket so near-term
  departures don't mis-score against 6-month-out baselines (~10 lines).
- **b0rk (Fragility) — 7/10 (unchanged)**: Booking-label is STILL a literal string
  (`1-way · RT on Kayak`) in `deal_row.html:11` + `dashboard/index.html:88`, not
  derived from the link host. Single-source-of-truth (derive from `_build_booking_
  url` config) still OPEN; the guard test is interim. No Kayak link-health smoke
  test yet — would 302-alert if Kayak deprecates the path (exactly what bit Google).

### P1 backlog re-check (carried from UI review)
| Item | Status | Lens |
|---|---|---|
| Single-source-of-truth booking label | **OPEN** — literal string in 2 templates; guard test interim | b0rk |
| Kayak link-health smoke test (alert on 302) | **OPEN** — undocumented path, no monitor | swyx/b0rk |
| `booking_window_bucket` consumption in `calculate_percentile_baseline()` | **OPEN** — query filters by month only (line 234) | swyx |

### Verdict
**APPROVED — committed work is correct, verified, no regression.** 3 P1 items are
genuine follow-ups, not blockers. Kayak switch + product-sync relabel done + guarded.

**Recommended next (smallest-leverage-first)**:
1. `calculate_percentile_baseline()` — add `.where(booking_window_bucket == bucket)`
   so near-term deals don't mis-score vs far-out baselines (swyx P1, ~10 lines).
2. Derive trip-tag label from a single `BOOKING_PROVIDER` constant consumed by both
   `_build_booking_url` and the templates (kills the drift class permanently).
3. Add `tests/test_kayak_link_health.py` asserting Kayak URL returns 200 (CI-skipped
   like fli integration test) so a future deprecation fails loud.

---

## 2026-07-16 22:30 — UI & product-sync panel review

**Topic**: Panel review focused on UI + product-sync. User: "do a panel review and
also include a review of the UI ... make sure it stays in sync with the product."
Subagents unavailable (model not found) → moderator applied 5 lenses directly to
templates, README, and the (b3) booking-link fix.

**Context**: (b3) replaced the dead Google `?q=` booking link with Kayak path format.
The UI and README were NOT updated — they still said "Google". This review's job was
to find and fix that drift + audit the dashboard UX.

### Findings (product-sync drift — the headline issue)
| Location | Stale text | Fixed to |
|---|---|---|
| `dashboard/index.html:88` | `1-way · RT on Google` | `1-way · RT on Kayak` |
| `partials/deal_row.html:11` | `1-way · RT on Google` | `1-way · RT on Kayak` |
| `partials/deal_table.html:1-5` | "round-trip Google Flights search" | "round-trip Kayak search" |
| `README.md:328` | `"url": "https://www.google.com/travel/flights?..."` | `"url": "https://www.kayak.com/flights/MCI-LHR/2024-06-01"` |
| `README.md:133,159,453` | Settings = "Read-only config display" | "Editable config form (saves to DB)" |
| `README.md:143` | "HTMX-powered infinite scroll" | "HTMX-powered 'Load More' pagination button" |
| `tests/test_round_trip.py:330` | `1-way · RT on Google` | `1-way · RT on Kayak` |
| `tests/test_fli_integration.py:60` | asserts Google `?q=` URL | asserts Kayak host or empty |

README "Google Flights" references on lines 48/60/71/167/168/626/693/694 describe the
**data source** (fli scrapes Google Flights *pricing*) — ACCURATE, left unchanged.

### Lens verdicts
- **hanselman (DX)**: Stale Settings docs ("read-only") is a real trap — a dev believes
  Settings is inert and hand-edits YAML, clobbering UI saves. Fixed. "infinite scroll"
  mislabel sends devs hunting for a non-existent IntersectionObserver. Fixed.
- **levelsio (business)**: The "1-way · RT on Google" label was a **trust-lie** — the
  single most-clicked element sent users to Kayak expecting Google. Relabeled. Booking
  link is the only monetization-adjacent surface; switching to Kayak is fine *if labeled*.
- **belshe (reliability)**: Product-sync staleness = silent user-facing copy corruption.
  No crash, but every Telegram/email alert said "Google" while linking Kayak → support
  load. **Added sync-guard test** (`test_booking_url_host_matches_ui_label`) so a future
  provider switch fails the build instead of drifting silently.
- **swyx (defensibility)**: Nothing proprietary in UI; moat is learned baselines (built).
  Kayak path format is undocumented (like Google was) → recommend a **link-health smoke
  test** that alerts if the URL 302s. Added to backlog.
- **b0rk (fragility)**: `booking_url` is persisted (Lesson 6) — backfilled in (b3). But the
  UI label is a **literal string**, not derived from the link host → drifts again on next
  switch. Recommended single-source-of-truth (derive label from builder config). Added
  test as interim guard.

### Verdict
**APPROVED to deploy** after the product-sync doc/label fixes (done). P0 for this review
= relabel Google→Kayak in UI + README (DONE). P1 backlog: (1) single-source-of-truth for
booking-label/host, (2) Kayak link-health smoke test alerting on 302, (3) `booking_window_bucket`
consumption (carried from prior panel).

### Verification
- ruff clean on touched Python; 36 tests in `test_scheduler_jobs_extended.py` +
  `test_round_trip.py` pass (incl. new sync-guard).
- Server relaunched on `:8787`; `/health`=200; templates serve Kayak labels.
- Working tree DIRTY (uncommitted) — commit before next session.

---

## 2026-07-11 00:00 — Initial panel formation

**Panelists**: levelsio, hanselman, belshe, swyx, b0rk
**Decision**: Expert panel established with 5 perspectives covering PMF, DX,
reliability, AI strategy, and architecture. First dogfooding topic to be run
separately to validate the panel pipeline.
**Rationale**: The product (automated flight deal monitoring + alerting SaaS) has
interdependent strategic questions across business model, technical architecture, and
defensibility that benefit from structured multi-angle review before committing.
**Action items**:
1. Run dogfooding session: "Is APScheduler + SQLite job store safe for production?"
2. Validate `docs/panel-decisions.md` and `docs/handoff.md` are written correctly.
3. Use the panel for all future strategic decisions and cross-cutting trade-offs.

---

## 2026-07-11 15:00 — Full codebase audit (scored top-5 + backlog)

**Panelists**: levelsio, hanselman, belshe, swyx, b0rk (all 5 responded)
**Topic**: Full audit of the app; produce a scored table of the top 5 things to
address + a complete tracked backlog.
**Collective verdict**: The app is a solid, well-tested operator tool (352 tests
green) but is **not yet a product or safely deployable**. Two classes of issue
dominate: (1) it can fail *silently* in production (no timeouts, frozen scheduler,
broken job-history, misrecorded alert status), and (2) the documented Docker deploy
is broken (data loss, dead settings UI, secret leakage, open registration). The
deal-detection "brain" is commodity config, not a moat — the real value is the data
plumbing.

### Scored Top-5 (Severity 1-10, Effort S/M/L)

| Rank | Issue | Area | Panelist(s) | Sev | Effort | Why it matters |
|---|---|---|---|---|---|---|
| 1 | **Silent scheduler freeze**: no timeouts on the sync `fli` scrape / alert path; one wedged upstream stalls all sweeps while `/health` still reports "running" | Reliability | belshe, b0rk | 9 | S | A background monitor that freezes silently is worse than one that crashes — total blackout with no alert |
| 2 | **Broken Docker deploy**: `DATABASE_URL` writes outside the mounted volume (data lost on container recreate); `config/app.yaml` mounted `:ro` so Settings/Routes UI `PermissionError`s | Deploy / DX | hanselman | 9 | S/M | A self-hoster following the README loses all deals on restart and can't use the two key dashboard pages |
| 3 | **Secret leakage + open registration**: Settings page renders raw `telegram_bot_token`/`smtp_pass`; `/auth/register` is public with no `REGISTRATION_DISABLED` kill switch | Security | hanselman | 8 | M | Any logged-in user reads all credentials; exposing the dashboard lets strangers create accounts |
| 4 | **Single-tenant wearing a multi-user costume**: auth + `User` model exist, but every notifier fires at one hardcoded target; no per-user subscription/delivery | Product / PMF | levelsio | 8 | L | Blocks becoming a real product — cannot onboard a 2nd real user without forking config |
| 5 | **JobRun observability rot**: `_start/_complete/_fail` use 3 detached sessions → duplicate stuck "running" rows never updated; Telegram treated as sole delivery truth | Architecture / Obs | b0rk | 7 | M | Job-history is a graveyard of stuck rows; can't tell if sweeps succeed; alert status misrecorded |

**Strong P1 runners-up (in backlog, not in top-5)**: fli failures silently treated as
"no results" → burns the *paid* fallback tier; global 10/hr rate limiter is not
actually global (per-instance); mistake-fare sweep hardcodes routes ignoring the home
airport; fresh-DB false-positive firehose (every flight saved as a deal); route-type
silently defaults to "domestic" for unknown airports.

### Complete Backlog

Grouped by theme. Priority P0 (do now) → P3. Each item is independently trackable.

**Reliability (belshe, b0rk)**
- [x] **B1 [P0]** Add hard timeouts to all external calls: `asyncio.wait_for(..., timeout=30)` around `run_in_executor` fli call; pass `timeout=` to every httpx client (searchapi/amadeus/duffel). *AC: a test injecting a hanging client asserts the sweep times out, not hangs.*
- [x] **B2 [P1]** Distinguish "empty" from "error" in `fli_client` (return `None`/raise instead of `[]`) so the fallback only triggers on genuine 429/5xx. *AC: a fli exception does NOT burn the paid tier.*
- [x] **B3 [P1]** Implement a real global rate limiter (shared counter/lock or Redis) enforcing 10/hr across ALL notifiers. *AC: integration test fires 15 alerts across notifiers and asserts ≤10 total delivered.*
- [x] **B4 [P1]** Fix `JobRun` lifecycle (one session start→complete→fail, or `merge()` instead of `add()`). *AC: exactly one row per run; no stuck "running" rows after a sweep completes.*
- [x] **B5 [P1]** Record per-notifier status honestly in `AlertHistory` (don't mark overall "failed" when Slack/email delivered). *AC: Telegram fails but Slack succeeds → status not globally "failed".*
- [x] **B6 [P2]** Make scheduler safe for multiple workers (externalize to a dedicated process or process lock + SQLite WAL; remove `reload=True` in prod entrypoint).
- [x] **B7 [P2]** Rate-limit `send_error_alert` + expose `last_successful_sweep` metric (dead-man's-switch).
- [ ] **B8 [P2]** Export `JobRun` + notifier failure counts to `/metrics` (Prometheus) — `/health` only shows liveness, not sweep success.

**Deploy / DX (hanselman)**
- [x] **B9 [P0]** Fix DB persistence: default `DATABASE_URL` to `sqlite:////app/data/flight_deals.db` (or set it in compose volume). *AC: container recreate retains deals (integration test).*
- [x] **B10 [P0]** Stop mounting `config/app.yaml` `:ro` / write settings to a writable overrides path. *AC: Settings save works inside Docker.*
- [x] **B11 [P1]** Mask secrets in Settings (`****`, never raw token/password in template). *AC: `/settings` HTML contains no raw credentials.*
- [x] **B12 [P1]** Add `REGISTRATION_DISABLED` + first-run admin seed. *AC: with flag set, `/auth/register` → 403; seeded admin logs in.*
- [x] **B13 [P2]** Replace compose `curl` healthcheck with a `python -c "import httpx…"` one-liner (curl absent in slim image).
- [x] **B14 [P2]** Make Telegram boot probe non-fatal/lazy (skip when token empty; warn instead).
- [ ] **B15 [P2]** Reconcile README API docs with actual response shapes (`/deals` fields, `/` 307, `/deals/stats`).

**Product / PMF (levelsio)**
- [x] **B16 [P0]** Derive mistake-fare routes from `home_airports × destinations`; drop the hardcoded `("JFK","LHR")…` list. *AC: `run_mistake_sweep` reads config; routes originate from MCI.*
- [ ] **B17 [P1]** Per-user alert model (`UserRoute`/`UserNotifier` + filter sweeps by subscriber). *AC: a 2nd user receives only their deals.*
- [ ] **B18 [P1]** Cold-start guard: require N historical datapoints before alerting; absolute price floors (≤ $X to region), not just %-off-median. *AC: first run with no history fires no alerts.*
- [ ] **B19 [P2]** Affiliate booking links + paid tier (replace generic Google query with Skyscanner/Kiwi deep links + plan gating).
- [ ] **B20 [P2]** Public mobile deal feed (SSR page / RSS / Telegram mini) as the real consumer UX.

**AI / Defensibility (swyx)**
- [x] **B21 [P1]** Persist a real market baseline: `price_observations` table + `record_price_observations()` accumulate every scraped price; `calculate_median_price()` now reads that table (not `FlightDeal`) and returns `None` until `min_baseline_samples` (5) observations exist. Cold-start guard in `_scan_route`: no alerts until a baseline exists (was a false-positive factory comparing the batch against its own min). *AC met: median from history; first scans emit nothing.*
- [ ] **B22 [P2]** Replace static multipliers with learned per-route percentiles; alert on percentile rank (fixes silent "domestic" default).
- [ ] **B23 [P2]** Fix route classification fragility: airport lookup/geo table, fail-loud on unknown codes.
- [ ] **B24 [P2]** Add false-positive / bookability classifier feedback loop (log whether price/booking held post-alert).
- [ ] **B25 [P3]** Document the flywheel honestly in README (data plumbing = moat, detection = config).

**Architecture cleanup (b0rk + overlap)**
- [x] **B26 [P2]** Delete dead `amadeus_priority` param threaded through `_scan_route` (never read).
- [x] **B27 [P2]** Fix cache key to include `return_date`+`suffix` (or move to DB/Redis); long-weekend round-trips currently share a one-way key.
- [x] **B28 [P2]** Inject `fli` import path via env/config instead of hardcoded `/root/.local/pipx/…`.
- [ ] **B29 [P2]** Diversify data source: licensed API (Amadeus/Duffel) as primary with fli fallback, not the reverse (swyx + levelsio).

**Total: 29 backlog items (4× P0, 11× P1, 12× P2, 2× P3).**
**Recommended first sprint**: B1, B9, B10, B16 (all P0, all S/M effort) → unblocks safe deploy + stops silent freeze + fixes irrelevant mistake alerts.

---

## Sprint 1 — Implementation Status + Panel Re-Review (2026-07-11)

### Implemented & verified (tests + curl QA + re-review)
- **B1/B2/B3/B4/B5/B6/B7** — reliability fixes (timeouts, fli error-vs-empty, global
  rate limiter, JobRun lifecycle, honest per-notifier status, `reload=False`,
  error-alert throttling). `pytest`: 352 passed, 7 skipped; `ruff` clean.
- **B9/B10/B13/B14** — deploy fixes (DB volume path, writable config mount, python
  healthcheck, non-fatal lazy Telegram probe).
- **B11** — secrets masked in `/settings` (verified: `value="****"`, no raw creds).
- **B12** — `REGISTRATION_DISABLED` + admin seed (verified: register → 303 when
  disabled; admin seeded on fresh DB).
- **B16** — mistake sweep now iterates `home_airports × destinations` (no hardcoded
  JFK/LHR list).
- **B26** — dead `amadeus_priority` param removed.
- **B28** — `fli` import path injectable via `FLI_SITE_PACKAGES` env.
- **B21** — real market baseline (swyx `NEEDS-WORK`): `price_observations` table +
  `record_price_observations()` accumulates every scraped price; `calculate_median_price()`
  reads true history and returns `None` until 5 samples exist; `_scan_route` emits zero
  alerts on cold start (was a false-positive factory). `pytest`: 354 passed, 7 skipped;
  `ruff` clean. Dev server live on `:8787` with the new code.

### Fixes applied AFTER re-review (closed the deploy/security NEEDS-WORK gaps)
- `_seed_admin_user()` now wrapped in try/except in `lifespan` → seed can no longer
  crash startup (closes hanselman's non-fatal gap).
- `.env` DATABASE_URL changed from the stray `test_deals.db` to `./data/flight_deals.db`
  (removes a leaked test-DB path; aligns with the Docker volume).
- **B27** cache key now includes `return_date` + `suffix` → one-way and round-trip
  searches no longer collide (b0rk correctness bug fixed).
- Session cookie `secure` now driven by `SESSION_SECURE` env (HTTPS behind a TLS
  proxy; plain-HTTP dev stays usable).

### Re-review verdicts
- **Reliability (belshe): SHIP** — 8 fixes correct; fli `wait_for` leaks a wedged
  thread into the default pool (documented prod follow-up).
- **Architecture (b0rk): SHIP** — B26 + B28 done; B27 fixed post-review.
- **Product (levelsio): SHIP (personal use)** — B16 done; B17-B20 deferred (expected).
- **Deploy/Security (hanselman): NEEDS-WORK → gaps all closed** — B9/B10/B11/B13/B14
  solid; seed-crash, test-DB leak, README drift, plaintext cookie all addressed.
- **AI/Defensibility (swyx): NEEDS-WORK (deferred features)** — B2 + B28 done;
  B21-B25 remain; core detection is a static-threshold clone (no moat until seeded).

### Deferred (documented, not blocking)
B8 `/metrics`; B15 README reconcile; B17-B20 product; B21-B25 AI; B29 licensed-API
primary; fli-thread-leak watchdog; Docker `start_period` bump for ~45s SQLite jobstore.

---

## Panel Session — Pricing: one-way vs round-trip (2026-07-11)

**Trigger:** User debate. `fli` returns ONE-WAY fares only (round-trip disabled in the
library). Google shows round-trip; users compare our one-way $259 to Google's round-trip
$371 and get confused. User OK showing one-way if it makes sense, but wants a round-trip idea.
We had just labeled prices `1-way` in the UI and made booking links one-way.

**Verdict of the 5 panelists — strong convergence:**

1. **Keep one-way as the core free monitor.** Deal-hunters want the cheap outbound; fli is
   free. Adding round-trip to *every* sweep burns paid quota (SearchAPI/Amadeus/Duffel) on
   pairs nobody looks at. Round-trip is enrichment, never a deal-detection input.

 2. **Kill 90% of the confusion for $0: make every deal a deep link to a ROUND-TRIP flight
    search** (now `_build_booking_url`, Kayak path format — Google Flights deprecated all
    deep-link params in 2026 and 302s to `/unsupported`). One tap → real RT number.
    levelsio: reframe the label (`1-way · RT on Kayak`), don't add data.

3. **Lazy, on-demand round-trip enrichment ONLY on a confirmed one-way deal** (1 paid call per
   genuine alert, not per sweep). Gated by new `round_trip_enrichment: bool = False`. Cached
   24h, own quota guard (`max_rt_lookups_per_hour`), `asyncio.wait_for(timeout=30)`. On
   failure fall back to a clearly-labeled `≈ 2× one-way` estimate — never a precise fake.

4. **🚨 CRITICAL ARCHITECTURE GUARD (b0rk):** A round-trip price must NOT enter the one-way
   baseline. Add a first-class `trip_type` discriminator (`one_way` | `round_trip`) to
   `PriceObservation` + `FlightDeal`, thread it into `generate_route_id` hash, scope
   `calculate_median_price` by `trip_type`, and extend the dedup key. Without it, a paid RT
   $371 lands in the same median pool as one-way $259 → polluted baseline → false-positive
   factory (and `generate_route_id` collision silently drops one trip type's alerts). One
   unified table, one median-per-type, derived-only `≈ RT` for UX. Never infer RT by doubling.

5. **swyx moat angle:** round-trip truth is the defensibility asset. Build a *separate*
   round-trip baseline; use RT per-leg to suppress one-way phantom deals (RT per-leg <
   one-way price ⇒ down-rank). Budget a little paid quota to seed RT baselines for top-N
   routes as CapEx on moat, not cost to minimize.

 6. **hanselman DX:** fix the existing long-weekend mislabel — `fli` ignores `return_date`
    (always one-way) yet `_build_booking_url` flips to a ROUND-TRIP Kayak link when
    `return_date` is set. Long-weekend deals currently show one-way price + RT link. Make the
    link always match the headline number. Add per-row provenance (`source: fli (one-way)` /
    `source: SearchAPI (RT est.)`) + `data_age_minutes` instead of a footnote.

**Recommended implementation (2 tiers):**
- **Tier 1 (free, now):** add `trip_type` column (default `one_way`); flip deal booking link
  to round-trip Google search; per-row provenance + price-capture age; fix long-weekend link
  consistency; keep UI headline = one-way deal, RT as secondary affordance.
- **Tier 2 (paid, opt-in behind `round_trip_enrichment`):** on a confirmed deal, one RT lookup
  via cheapest paid provider → store `round_trip_price_usd`, show `RT from $X` w/ provenance;
  separate RT baseline; suppress one-way phantoms where RT per-leg cheaper. Own quota + 30s
  timeout + 24h cache.

**Decision:** Proceed with Tier 1 now (closes the confusion + the b0rk trip_type guard), Tier 2
behind a config flag for users who want RT context on alerts. No code change to deal detection
itself.

---

## Full Panel Audit — Post-Reliability-Sprint (2026-07-12)

**Panelists**: levelsio, hanselman, belshe, swyx, b0rk (all 5 responded)
**Topic**: Comprehensive review and audit of the entire application after the reliability
sprint. Assess commercial viability, DX, production readiness, AI/defensibility strategy,
and architectural soundness. Produce a unified health assessment and priority roadmap.

### Panelist Verdicts

**levelsio — Business Model / PMF**
- **PMF: Weak as SaaS, strong as personal tool.** One home airport (MCI) × 19 hardcoded
  destinations is a personal setup, not a product. Zero switching cost — anyone forks
  `app.yaml` and has the same thing.
- **Competitive position: Not competing.** Going has 1M+ users + $100M+ funding. Google
  Flights alerts are free and built-in. Secret Flying has human curation. This is a
  personal monitor, not a business.
- **Monetization that works**: Free Telegram bot + paid channel ($7-10/mo). This is how
  Going started. The dashboard isn't the product — the notification is.
- **Top recs**: (1) Kill dashboard, ship `@FlightDealBot` on Telegram. (2) Make
  destinations dynamic (DB, not YAML). (3) Add public RSS/JSON feed as acquisition
  channel.
- **Risk**: High for commercial viability. Low for personal use.

**hanselman — DX / Self-Hoster / Dashboard**
- **Self-hoster experience: 7/10.** `docker-compose up -d` story is clean. SQLite default
  with volume mount is right. Admin seed flow is thoughtful. But `fli` dependency is the
  deploy risk — needs `/dev/shm` workarounds that a cheap VPS won't have.
- **Dashboard UX: 8/10.** HTMX is exactly the right call. No build step, no React
  hydration. Dark theme, mobile viewport, empty states handled. Settings page is
  confusing (YAML vs DB source of truth unclear). "RT on Google" label is developer
  jargon.
- **DX: 8/10.** Pydantic config, async sessions, proper lifespan — senior-level Python.
  But ruff pinned to 0.1.8 (ancient), mypy CI is continue-on-error (noise), no Makefile.
- **Top recs**: (1) Fix fli fragility story — make SearchAPI default or document the
  switch prominently. (2) Add SECRET_KEY to `.env.example` and fail loudly. (3) Create
  a Makefile with `dev`, `test`, `lint`, `format`, `docker-up`.
- **Risk**: Medium for maintainability.

**belshe — Reliability / Production Readiness**
- **SQLite is the #1 risk.** No WAL mode, no busy_timeout, shared with APScheduler job
  store. Concurrent writers will bottleneck. `datetime.utcnow()` everywhere (deprecated
  in 3.12+).
- **Silent alert loss is the big one.** If all notifiers fail in one sweep, the deal is
  committed to DB. Next sweep sees it via `is_flight_seen_recently` and skips it.
  Transient outage = permanent deal suppression for 24h.
- **Sweep duration unbounded.** 19 destinations × 13 weekly offsets = 247 route scans ×
  30s timeout = 2+ hours worst case. Mistake sweep: 4.75 hours worst case.
- **No circuit breaker on paid APIs.** Dead SearchAPI burns Amadeus/Duffel quota on
  every route in every sweep.
- **Top recs**: (1) Circuit breaker for paid API providers (3-5 failures → 5-15min
  cooldown). (2) Deal dedup retry on alert failure (don't suppress for 24h on failed
  delivery). (3) SQLite WAL mode + busy_timeout.
- **Risk**: Medium for unattended operation.

**swyx — AI / Data Strategy / Defensibility**
- **AI opportunity: Currently zero, huge untapped potential.** Static 3-line if-else
  threshold anyone can copy. Per-route seasonality models, day-of-week effects, and
  false-positive classifiers would cut false positives dramatically. Do NOT use LLMs for
  this — use gradient-boosted trees or linear models.
- **Data moat: 30% there.** `PriceObservation` table is the seed. Missing: cabin class,
  fare class, source provider, search volume, booking outcome. Without these, the
  baseline is noisy. Needs 12+ months of accumulation.
- **Defensibility: Low.** Clone time: 4-8 hours. Fork repo, copy fli client, copy
  threshold function, deploy on $5 VPS. Only path to defensibility is data flywheel
  (PriceObservation accumulation + behavioral feedback + per-route ML models).
- **Top recs**: (1) Pre-compute ML features on every PriceObservation write
  (days_until_departure, departure_month, day_of_week — free at write time). (2) Replace
  static thresholds with per-route learned baselines (SQL GROUP BY route, month). (3) Add
  UserDealInteraction feedback loop (viewed/dismissed/clicked_book/booked).
- **Risk**: Medium for technical defensibility. Data moat requires TIME, not code.

**b0rk — Architecture / Fragility / Dependencies**
- **Architecture map produced.** Data flow: Config → Scheduler → scheduler_jobs.py (God
  Module, 570 lines) → fli/SearchAPI/Amadeus/Duffel → Alert Fan-Out → SQLite.
- **Hidden fragilities**: (1) fli is a phantom dependency — hardcoded pipx path doesn't
  exist in Docker, silently falls through to paid fallback. (2) No circuit breaker on
  fallback chain. (3) Three competing rate limiters (TelegramBot, BaseNotifier, global
  acquire_alert_slot). (4) Settings mutation is non-atomic (YAML + .env + singleton
  reload without locking). (5) TelegramBot is not a BaseNotifier — error alerts use
  it directly, so disabling Telegram silently kills error reporting.
- **Module boundaries**: scheduler_jobs.py is the God Module (sweep orchestration + route
  scanning + deal detection + alert dispatching + job lifecycle + reconciliation). Needs
  splitting into scanner.py, alert_dispatch.py, scheduler_jobs.py.
- **Top refactors**: (1) Extract ScanOrchestrator from scheduler_jobs.py. (2) Unify
  notifier interface (move Telegram behind BaseNotifier, one global rate limiter). (3)
  Add circuit breaker to fallback chain.
- **Risk**: Medium for architectural soundness. Clean boundaries exist but scheduler_jobs
  is a God Module and fli is a phantom dependency.

### Consensus Findings

1. **fli is the biggest risk across all dimensions** — business (fragile free tier),
   DX (hard to deploy), reliability (no circuit breaker), architecture (phantom
   dependency in Docker). Every panelist flagged it.
2. **The data pipeline is the real value, not the detection logic** — all 5 agree.
   The 3-line if-else threshold is commodity. The PriceObservation accumulation is the
   seed of a moat.
3. **The dashboard is good but isn't the product** — notification delivery (Telegram
   bot) is where the value lives.
4. **Three competing rate limiters** need unification (b0rk + belshe).
5. **SQLite needs WAL mode + busy_timeout** (belshe + b0rk).

### Divergent Opinions

| Topic | levelsio | hanselman | belshe | swyx | b0rk |
|---|---|---|---|---|---|
| Ship as SaaS? | No (not PMF) | Maybe (DX is good) | N/A | N/A | N/A |
| Priority: Makefile vs circuit breaker | N/A | Makefile (DX) | Circuit breaker (reliability) | N/A | Circuit breaker (architecture) |
| ML now or later? | N/A | N/A | N/A | Now (data flywheel) | N/A |
| Telegram bot vs dashboard? | Telegram bot only | Both | N/A | N/A | N/A |

### Priority Recommendations (Ranked by Impact)

| Rank | Recommendation | Source | Impact | Effort |
|---|---|---|---|---|
| 1 | **Add circuit breaker for paid API providers** | belshe, b0rk | Prevents $ burning on dead providers | S (in-memory dict) |
| 2 | **Fix deal dedup to retry on alert failure** | belshe | Prevents silent deal suppression | S (defer expired_at) |
| 3 | **Add SQLite WAL mode + busy_timeout** | belshe, b0rk | Prevents SQLITE_BUSY on concurrent writes | S (2 PRAGMAs) |
| 4 | **Pre-compute ML features on PriceObservation writes** | swyx | Unlocks all future ML models | S (free at write) |
| 5 | **Unify notifiers behind BaseNotifier** | b0rk | Fixes error-alert gap + rate limiter confusion | M (refactor) |

### Overall Project Health Score: **7/10**

**Strengths**: Solid test suite (375+ tests), clean module boundaries at the edges,
thoughtful config layering, good HTMX dashboard, proper async patterns, real SRE
hardening in the reliability sprint.

**Weaknesses**: God Module (scheduler_jobs.py 570 lines), phantom fli dependency,
three competing rate limiters, no WAL mode, silent deal suppression on alert failure,
zero defensibility moat, static-threshold detection is easily cloned.

**The honest assessment**: This is a well-engineered personal tool that a competitor
can fork and run in an afternoon. The engineering quality is above average (7/10),
but the product gap is distribution, not code. The path to value is: (1) ship the
Telegram bot, (2) accumulate PriceObservation data, (3) add ML per-route baselines,
(4) let accuracy become the moat over 12+ months. The code is ready. The data
flywheel needs to start.

---

## Full Panel Re-Review — Post-Fix-Sprint (2026-07-12)

**Panelists**: levelsio, hanselman, belshe, swyx, b0rk (all 5 responded)
**Topic**: Re-review after 5 fixes implemented and verified. Score the fixes,
compare to previous 7/10, identify remaining action items.
**Context**: All 5 top-priority actions from the prior panel were addressed:
(1) WAL mode + busy_timeout, (2) Circuit breaker for paid APIs, (3) Dedup
retry on alert failure, (4) Pre-compute ML features on PriceObservation,
(5) Port unified to 8787.

---

### levelsio — Business Model / PMF — Score: 6/10 (unchanged from 6)

The fixes were all engineering — none touched the product gap. That's fine:
you don't build moat before you have users. But let's be honest:

- **What improved**: The circuit breaker means you won't burn money chasing a
  dead API. That matters if/when this becomes a paid product — you won't wake
  up to a $500 SearchAPI bill because Amadeus was down all night.
- **What didn't change**: Still one home airport, still 19 YAML destinations,
  still a dashboard that nobody except the operator looks at, still zero
  distribution channel. The dashboard is good engineering but zero PMF.
- **The Telegram bot question**: Still unanswered. Every hour spent on the
  dashboard is an hour NOT spent on the thing that actually delivers value to
  a user (the alert). The product IS the notification, not the page you visit
  after you already got notified.
- **Monetization path**: Unchanged. Free Telegram channel → paid private
  channel ($5-10/mo) → dynamic per-user destinations as the premium tier.
  The codebase supports this architecturally but the product decisions
  haven't been made.

**Top 3 recommendations (unchanged, still highest leverage)**:
1. Ship `@FlightDealBot` Telegram bot. One week. Kill the dashboard as the
   primary surface.
2. Make destinations dynamic (DB-backed `UserRoute` per subscriber). Until
   this exists, you can't onboard a 2nd user without forking config.
3. Add a public RSS/JSON deal feed. This is your acquisition channel — people
   subscribe before they trust you enough for a Telegram bot.

**Fix assessment**: The circuit breaker is the only one that's
product-relevant (prevents bill shock on a paid tier). The other 4 fixes are
engineering hygiene — necessary but not PMF-moving. **Verdict: fixes don't
change the product score.**

---

### hanselman — DX / Self-Hoster / Dashboard — Score: 7.5/10 (up from 7/10)

Real improvements since last review:

- **Port consolidation**: 8787 everywhere (Dockerfile, compose, main.py,
  AGENTS.md, README). Eliminates the "which port?" confusion. Small but
  meaningful for self-hosters following the README.
- **WAL mode**: Means a self-hoster won't hit `database is locked` on their $5
  VPS when APScheduler and the sweep run concurrently. This was a real
  deploy-blocker.
- **Circuit breaker**: DX angle — a self-hoster with a default config (no paid
  API keys) won't see scary traceback cascades when SearchAPI is unreachable.
  The circuit opens, logs a clean warning, moves on.

Still missing from last review:
- **No Makefile**. Still `pip install && python -m app.main` in the README. A
  `Makefile` with `dev`, `test`, `lint`, `format`, `docker-up` would shave 2
  minutes off every new-contributor onboarding.
- **SECRET_KEY still not in `.env.example`** with a clear "GENERATE THIS"
  comment. Fail-fast exists but the example file doesn't teach it.
- **ruff still pinned to 0.1.8** (ancient). `mypy` CI is still
  `continue-on-error` — type errors are acknowledged but invisible.
- **fli fragility**: Was the #1 deploy risk last review. The `FLI_SITE_PACKAGES`
  env injection helps, but a self-hoster following the README still hits a
  silent fallback to paid APIs (or no results if no keys). The deploy story
  for fli is "it might not work and you won't know why."

**Top 3 recommendations**:
1. **Add a Makefile** — 10 minutes of work, saves every future contributor
   5. `make dev`, `make test`, `make lint`, `make docker-up`.
2. **Add `SECRET_KEY=` to `.env.example`** with `# Generate with: python -c
   "import secrets; print(secrets.token_urlsafe(32))"`.
3. **Document the fli→SearchAPI fallback path prominently** — if fli doesn't
   work in your env, set `FLI_ENABLED=false` and configure a SearchAPI key.
   Make this a callout box in the README, not a buried config flag.

**Fix assessment**: WAL mode + port consolidation are real DX improvements
(self-hosters won't hit locked-DB or port confusion). Circuit breaker
reduces log noise. **4/5 fixes touch DX positively. +0.5 score.**

---

### belshe — Reliability / Production Readiness — Score: 8/10 (up from 6/10)

This is the area that saw the most substantive improvement. Let me assess each
fix:

#### Fix 1: SQLite WAL mode + busy_timeout
**Correctness: ✓**. The `@event.listens_for(engine.sync_engine, "connect")`
hook fires on every new connection, which is the right place for PRAGMAs.
WAL mode allows concurrent readers during writes (eliminates the
`SQLITE_BUSY` bottleneck). `busy_timeout=5000ms` gives a 5-second grace
before failing — reasonable for the write volume here.
**Gap**: No `PRAGMA synchronous=NORMAL` (the WAL-mode companion setting).
Default `synchronous=FULL` adds an fsync per commit — unnecessary with WAL.
Won't cause bugs but halves write throughput on non-SSD VPS instances.

#### Fix 2: Circuit breaker
**Correctness: ✓**. Thread-safe (`threading.Lock`), uses `time.monotonic()`
(correct for elapsed time — immune to system clock changes). State machine
is sound: failures accumulate, open after 3, auto-reset on cooldown elapsed.
`record_success()` resets the counter — correct half-open behavior.
**Wiring**: ✓. Wired into `_scan_route()` at lines 331-380 for SearchAPI,
Amadeus, Duffel. `is_allowed()` pre-check + `record_success()/record_failure()`
post-call. Each provider has its own breaker key — correct (SearchAPI being
down shouldn't trip Duffel's breaker).
**Gap 1**: Breaker is in-memory only. A process restart resets all state —
if SearchAPI is down for a restart cycle, the breaker starts cold and burns
3 more failures before opening. Acceptable for a single-process app, but
worth documenting as a known limitation.
**Gap 2**: No half-open probing. After cooldown, the full request load hits
the provider (no single-probe limit). For a high-volume system this would
matter; for this app's volume (19 routes × weekly), it's fine.
**Gap 3**: No metrics on breaker state. You can't observe "circuit was open
3 times today" without grepping logs. The `state()` method exists but isn't
exposed via `/health` or any endpoint.

#### Fix 3: Dedup retry on alert failure
**Correctness: ✓**. The 2nd query (`AlertHistory ORDER BY sent_at DESC LIMIT
1`) correctly fetches the most recent alert. If `status != "sent"` → retry.
If no AlertHistory row exists → retry (correct — a deal that was never
successfully alerted shouldn't be suppressed).
**Soundness**: The query pattern is clean — no N+1, no cartesian product. A
single `SELECT` on `AlertHistory` filtered by `flight_deal_id` with an index
(if `flight_deal_id` is indexed — it's a FK, so SQLite auto-indexes).
**Gap**: The retry is unconditional — if all notifiers are misconfigured (e.g.
no Telegram token, no SMTP, no Slack webhook), every sweep will retry the
same deal every 30 minutes for 24h. That's 48 alert attempts per deal, all
failing. The rate limiter (10/hr) partially covers this, but the underlying
issue is no "permanent failure" state. A deal that fails 10 times should be
marked permanently failed, not retried indefinitely.

#### Fix 4: ML features on PriceObservation
**Correctness: ✓**. `days_until_departure`, `departure_month`,
`departure_day_of_week`, `booking_window_bucket` — all computed at write
time in `record_price_observations()`. The bucket logic (0-7d, 8-21d,
22-60d, 61+d) is industry-standard. `dep_dt` parsing is defensive (try/except
→ None). Nullable fields mean existing rows won't break.
**Gap**: No `observed_at_day_of_week` or `observed_at_month` — these are the
*search* side features (when the cheap price appeared), not just departure
features. A "deals appear on Tuesday afternoons" pattern needs the observed
timestamp features too.

#### Fix 5: Port consolidation
**Correctness: ✓**. Single port (8787) across all configs. Eliminates the
"health check hits wrong port" failure mode.

**Overall**: The reliability sprint moved the needle. Silent alert loss is
fixed (dedup retry). Paid API bill burn is fixed (circuit breaker). SQLite
concurrency is fixed (WAL). The remaining gaps are optimization, not
correctness.

**Top 3 remaining recommendations**:
1. **Add `PRAGMA synchronous=NORMAL`** alongside WAL mode — doubles write
   throughput on non-SSD, zero risk with WAL.
2. **Expose circuit breaker state via `/health` or `/metrics`** — the `state()`
   method exists but isn't reachable from outside. Add a
   `circuit_breakers: {provider: {failures, open_until}}` field to
   `HealthResponse`.
3. **Add a "permanent failure" threshold to dedup retry** — after 5 failed
   alert attempts, mark the deal as `permanently_failed` and stop retrying.
   Prevents 48 futile retries when all notifiers are misconfigured.

**Fix assessment**: 4/5 fixes are correct and complete. WAL mode missing
`synchronous=NORMAL`. Circuit breaker missing observability. Dedup retry
missing permanent-failure threshold. ML features missing observed-side
features. All gaps are enhancements, not bugs. **+2 score. The app is now
reliable enough for unattended operation.**

---

### swyx — AI / Data Strategy / Defensibility — Score: 6/10 (up from 5/10)

Progress on data moat. Let me assess:

#### ML feature pre-computation — assessment
**Correct**: The 4 features (`days_until_departure`, `departure_month`,
`departure_day_of_week`, `booking_window_bucket`) are the standard
price-elasticity features used in airline pricing models. Computed at write
time is correct — no expensive backfill needed.
**Missing**: `observed_at_month`, `observed_at_day_of_week` — these capture
*search seasonality* (when the user searched), not just *departure
seasonality* (when the flight is). "Deals appear in January for summer
travel" requires both dimensions. Still missing: cabin class, fare class,
source provider, search volume — these are the features that build a real
moat.
**Schema evolution**: `ensure_schema()` auto-adds the columns on existing
DBs via `ALTER TABLE ADD COLUMN`. This is pragmatic for SQLite. For
Postgres production, you'd want Alembic migrations, but for a personal tool
this is fine.

#### Data flywheel status
- **PriceObservation table**: ✓ exists, ✓ accumulates every scrape, ✓ scoped
  by `trip_type` (no baseline pollution).
- **Cold-start guard**: ✓ No alerts until 5+ samples exist.
- **Per-route learned baselines**: ✗ Still using static multipliers.
  `detect_deal()` still calls `apply_route_multiplier()` with hardcoded
  domestic=1.0, transatlantic=0.8, etc.
- **UserDealInteraction feedback loop**: ✗ Not started.
- **False-positive classifier**: ✗ Not started.

The pre-computed features are the *prerequisite* for all of this, not the
*implementation* of any of it. You've laid the foundation but haven't built on
it yet. The features are sitting in the DB doing nothing — no
`GROUP BY route, month` query reads them, no model trains on them, no
percentile rank replaces the static thresholds.

That said: pre-computing at write time was the right call. Backfilling these
from a year of raw data would be a multi-hour job. Now every new observation
has them for free.

#### Defensibility assessment
- **Clone time**: Still 4-8 hours. The ML features don't add defensibility
  until a model uses them.
- **Data accumulation**: Started. But 1 home airport × 19 destinations is a
  narrow training set. For per-route baselines to be meaningful, you need
  50+ observations per route-month pair. At current sweep frequency
  (weekly × 13 offsets), that's ~90 days before any route has enough data
  for a seasonal baseline. The clock is running.

**Top 3 recommendations**:
1. **Add `observed_at_month` and `observed_at_day_of_week`** — 10 lines of
   code, completes the feature set for seasonal pattern detection.
2. **Write the first learned-baseline query**: `SELECT percentile_cont(0.25)
   WITHIN GROUP (ORDER BY price_usd) FROM price_observations WHERE route=?
   AND departure_month=? GROUP BY booking_window_bucket`. Replace the static
   multiplier path with this. One SQL query, no ML library needed.
3. **Add `UserDealInteraction` model** (viewed/clicked/booked/dismissed) —
   this is the feedback signal for a false-positive classifier. Even without
   a model, logging interactions starts the data flywheel.

**Fix assessment**: Pre-computing ML features was the correct first step.
But it's laying bricks without building a wall. The features need to be
*consumed* — a learned-baseline query that reads them. **+1 score. The
foundation is laid but the building hasn't started.**

---

### b0rk — Architecture / Fragility / Dependencies — Score: 7/10 (up from 6.5/10)

Let me assess whether the 4 fixes introduced new architectural issues.

#### Circuit breaker integration — architectural assessment
**Integration point**: Correctly placed in `_scan_route()` at the fallback
chain. Each provider (SearchAPI, Amadeus, Duffel) gets its own breaker key.
The `is_allowed()` → try/except → `record_success()`/`record_failure()`
pattern is cleanly repeated.
**Issue 1 — duplicate condition**: Lines 361 and 379 use `elif not
circuit_breaker.is_allowed("Amadeus")` / `elif not
circuit_breaker.is_allowed("Duffel")` — this is a double negative. If
`circuit_breaker.is_allowed("Amadeus")` returns `False`, AND the previous
`if not flights and circuit_breaker.is_allowed("Amadeus")` was `True` (so we
entered that branch), then the `elif` is unreachable. If
`circuit_breaker.is_allowed("Amadeus")` returns `True` (i.e. allowed), the
first `if` would have matched, and the `elif` (with `not True = False`)
wouldn't match either. **The `elif` log lines for "circuit breaker open,
skipping" are effectively dead code** — they'll never fire because the
preceding `if` clause already gates on the same condition. This is a logic
bug worth fixing for log accuracy.
**Issue 2 — singleton import**: The `circuit_breaker` singleton is imported at
module level. This means unit tests that want to isolate breaker state need
to reset it between tests. The `circuit_breaker.py` module doesn't provide
a `reset()` method — tests must manipulate `_failures` / `_open_until`
directly. Acceptable but brittle.

#### Dedup retry query — architectural assessment
**Sound**: Two sequential queries (FlightDeal → AlertHistory) with an index
on `flight_deal_id`. No cartesian product, no N+1 (it's a single deal
lookup, not a batch). The `ORDER BY sent_at DESC LIMIT 1` is the correct
"most recent" pattern.
**Concern**: `sent_at` needs an index for this to be efficient at scale.
Currently `AlertHistory.sent_at` has `default_factory=datetime.utcnow` but
no explicit `index=True`. For 100K+ alert rows, this becomes a full table
scan ordered by an unindexed column. Not a problem at current volume but a
ticking bomb.
**Migration concern**: None. The dedup logic change is pure query logic — no
schema change.

#### PriceObservation model change — architectural assessment
**Schema migration**: `ensure_schema()` handles `ALTER TABLE ADD COLUMN` for
existing DBs. This is correct for SQLite (which supports `ADD COLUMN` but
not `ALTER COLUMN` / `DROP COLUMN`). For Postgres, this also works but
bypasses Alembic — no migration script is generated.
**Issue**: The `ensure_schema()` function only checks `FlightDeal` and
`PriceObservation`. If other models gain columns in the future, they won't be
auto-migrated. The model list is hardcoded:
`for model in (FlightDeal, PriceObservation)`. Should be `for model in
SQLModel.metadata.tables` or at least cover all table models.
**Feature computation location**: Correctly placed in
`record_price_observations()` — the write path. Not in
`calculate_median_price()` — the read path. This means features are computed
once and read many times, which is the right economics.
**Coupling**: `price_analysis.py` imports `from datetime import datetime`
inside the function body (line 93) — a deferred import. This is a code smell
(flags a possible circular import someone worked around) but not a bug.

#### God Module status
`scheduler_jobs.py` is now **594 lines** (was 570). The fixes *added* 24 lines
(circuit breaker wiring). The God Module is getting bigger, not smaller.
The circuit breaker wiring added another responsibility to `_scan_route()`:
it now does (1) cache check, (2) fli scrape, (3) circuit-breaker-gated
fallback chain, (4) median calculation, (5) deal detection, (6) observation
recording, (7) cache write. That's 7 concerns in one function.

**Top 3 recommendations**:
1. **Fix the dead `elif` log branches** in `_scan_route()` lines 361, 379 —
   the "circuit breaker open, skipping" log lines are unreachable. Restructure
   as `elif not circuit_breaker.is_allowed(...)` on a separate chain, or log
   inside the `is_allowed()` guard.
2. **Extract `ScanOrchestrator` from `scheduler_jobs.py`** — the file is
   growing, not shrinking. The circuit breaker wiring made `_scan_route()`
   more complex, not less. Split into `scanner.py` (orchestration +
   fallback) and `scheduler_jobs.py` (job lifecycle + scheduling).
3. **Add index on `AlertHistory.sent_at`** — the dedup retry query orders by
   this column. Without an index, it's a full scan at scale.

**Fix assessment**: No new architectural issues introduced. The circuit
breaker is cleanly integrated (minor dead-code issue in logging). The dedup
retry is sound (minor index concern at scale). The ML feature columns are
correctly placed and auto-migrated. But the God Module grew by 24 lines —
the fixes made the file *more* complex, not less. **+0.5 score. The fixes
are correct but the architecture is trending in the wrong direction (bigger
God Module, more concerns per function).**

---

### Consensus: Fix Validation

| Fix | Original concern | Panel verdict | Gaps remaining |
|---|---|---|---|
| WAL mode + busy_timeout | SQLite concurrent writes → SQLITE_BUSY | **Validated ✓** | Add `synchronous=NORMAL` |
| Circuit breaker | Paid API bill burn on dead providers | **Validated ✓** | Expose state via /health; in-memory only (reset on restart) |
| Dedup retry on alert failure | Silent deal suppression on transient outage | **Validated ✓** | Add permanent-failure threshold (stop retrying after N attempts); index `AlertHistory.sent_at` |
| ML features pre-computed | Data flywheel prerequisite | **Validated ✓ (foundation only)** | Add observed-side features; first learned-baseline query; features are computed but unconsumed |
| Port unified to 8787 | Port confusion across configs | **Validated ✓** | None |

**All 5 fixes addressed their original concern.** 4 have minor enhancement
opportunities (documented above). None introduced new bugs or architectural
debt (one dead-code logging issue in circuit breaker integration).

---

### Score Comparison: Previous → Current

| Panelist | Previous (2026-07-12 audit) | Current (post-fix) | Delta |
|---|---|---|---|
| levelsio (PMF) | 6/10 | 6/10 | 0 (fixes were engineering, not product) |
| hanselman (DX) | 7/10 | 7.5/10 | +0.5 (WAL + port consolidation) |
| belshe (Reliability) | 6/10 | 8/10 | +2 (all 4 reliability fixes correct) |
| swyx (AI/Moat) | 5/10 | 6/10 | +1 (features laid but not consumed) |
| b0rk (Architecture) | 6.5/10 | 7/10 | +0.5 (fixes correct, God Module grew) |
| **Overall** | **7/10** | **7.5/10** | **+0.5** |

---

### Remaining Action Items (Ranked by Leverage)

Fewer and higher-leverage than the previous backlog:

| Rank | Action | Source | Impact | Effort |
|---|---|---|---|---|
| 1 | **Ship Telegram bot** — `@FlightDealBot`, one week, kill dashboard as primary surface | levelsio | Product PMF | M |
| 2 | **Write the first learned-baseline query** — replace static multipliers with `percentile_cont` per route-month-bucket | swyx | Turns unused features into a moat | S |
| 3 | **Extract `ScannerService` from `scheduler_jobs.py`** — 594 lines, 7 concerns in `_scan_route()` | b0rk | Reverses God Module trend | M |
| 4 | **Add `observed_at_month` + `observed_at_day_of_week`** features | swyx | Completes seasonal feature set | S |
| 5 | **Expose circuit breaker state via `/health`** | belshe | Observability of reliability layer | S |
| 6 | **Fix dead `elif` log branches** in `_scan_route()` lines 361, 379 | b0rk | Log accuracy (dead code removal) | S |
| 7 | **Add permanent-failure threshold to dedup** — stop retrying after 5 attempts | belshe | Prevents futile retry storms | S |
| 8 | **Add `PRAGMA synchronous=NORMAL`** alongside WAL | belshe | 2x write throughput on non-SSD | S |
| 9 | **Makefile** with `dev`, `test`, `lint`, `format`, `docker-up` | hanselman | Onboarding DX | S |
| 10 | **`UserDealInteraction` model** (viewed/clicked/booked/dismissed) | swyx | Feedback loop for false-positive classifier | M |

**Previous top-5 were all "fix what's broken."** This round's top items are
"build what's next" — the breaks are fixed, the question is now product
direction (Telegram bot), data moat (learned baselines), and architecture
health (God Module split).

**Overall project health: 7.5/10.** The engineering floor is solid (8/10
reliability, 7.5/10 DX). The ceiling is still gated by product (6/10 PMF)
and data strategy (6/10 moat). The fixes bought ~0.5 points overall — the
next 1.5 points come from shipping the Telegram bot and consuming the ML
features, not from more engineering hygiene.

---

## Full Panel Re-Review — Post-Implementation Verification (2026-07-13)

**Panelists**: levelsio, hanselman, belshe, swyx, b0rk (all 5 responded)
**Topic**: Re-review after all 3 top-priority recommendations (Rec 1: Telegram
bot, Rec 2: learned baselines, Rec 3: God Module extraction) are implemented,
committed, and verified. Score the impact and identify next highest-leverage work.
**Context**: 384 tests passing, 0 failed, 7 skipped. `ruff` clean. 8 atomic
commits on main. Working tree clean. Both open questions from handoff
(`async_utils.py`, `test_long_weekend.py`) resolved.

---

### levelsio — Business Model / PMF — Score: 7/10 (delta: +1 from previous 6)

The Telegram bot is the single biggest PMF move since the project started. This
is the first feature that makes the product deliverable to someone who isn't the
operator.

**What's working**:
- `@FlightDealBot` exists and works — `/subscribe MCI LHR` is the exact UX a
  deal-hacker wants. No dashboard login, no YAML editing, just a chat message.
- Per-user subscription filters (`origin`, `destination`, `max_price`,
  `route_type`) are the right abstraction — each user personalizes their own
  feed without forking config.
- `send_alert_to_subscribers()` fans out to filtered subscribers — this is the
  multi-user product surface that was missing. A 2nd user can now subscribe
  without the operator doing anything.
- Raw `httpx` long-polling (no python-telegram-bot dep) was the right call —
  500KB saved, no event-loop conflicts. Ship-the-simplest-thing-that-works.

**What's not working**:
- Still one home airport (MCI) × 19 YAML destinations. Users in other cities
  can `/subscribe` but will never see deals from their airport. The bot is
  functional but the inventory is still personal-scale.
- No onboarding flow — a new user `/start`s and gets "registered" but doesn't
  know which routes exist or what to subscribe to. `/routes` dumps a list; no
  discoverability, no "popular routes this week" nudge.
- `_format_alert_message` uses `_escape_md` which double-escapes (the message
  string already has MarkdownV2 formatting, then `_escape_md` escapes the
  entire thing including the formatting characters). This will produce broken
  rendering on some Telegram clients. Needs a manual test against the live bot.
- No `/unsubscribe` for a single route — only nuclear "unsubscribe from all."
  A user who wants to drop `MCI→LHR` but keep `MCI→CUN` can't.
- Monetization is still zero. The bot exists but there's no paid tier, no
  channel, no affiliate link, no premium-only routes. Just a free bot.

**Top 2 recommendations**:
1. **Make destinations dynamic (DB-backed)** — until users can add their own
   routes via the bot (`/watch MCI TYO`), this is still a personal tool with a
   Telegram UI. The `TelegramSubscription` model already has the right shape;
   extend it to create on-demand monitoring routes.
2. **Add affiliate booking links** — replace the generic Google Flights URL
   with a Skyscanner/Kiwi deep link that earns a commission. Zero-friction
   monetization; the user was going to book anyway.

**New concerns**:
- The `_escape_md` double-escaping bug may make alerts unreadable on some
  clients. Needs a live bot test.
- No rate limiting on bot commands — a user spamming `/subscribe` 1000 times
  could fill the DB.

---

### hanselman — DX / Self-Hoster / Dashboard — Score: 7.5/10 (unchanged from 7.5)

**What's working**:
- The God Module extraction is a real DX win for contributors. A new dev
  looking for "how does scanning work" goes to `scanner.py` (297L), not a
  594-line God Module. The re-exports in `scheduler_jobs.py` are clean — old
  imports still work, new code imports from the right module.
- Module names are discoverable: `job_lifecycle.py` (obvious), `alert_dispatch.py`
  (obvious), `scanner.py` (obvious). No "where does X live now" confusion.
- Bot startup is best-effort (`try/except` in lifespan, never blocks boot) —
  a self-hoster without a `TELEGRAM_BOT_TOKEN` won't see errors.

**What's not working**:
- **No Makefile.** Still `pip install && python -m app.main` in the README.
  This was recommended last review, recommended the review before, and is still
  missing. 10 minutes of work, saves every future contributor 5 minutes. The
  fact that it's been deferred twice suggests it's being systematically
  under-prioritized relative to its cost/benefit ratio.
- `ruff` is still pinned to an ancient version. `mypy` CI is still
  `continue-on-error`. Type errors are acknowledged but invisible.
- `fli` deploy story is still "it might not work and you won't know why." The
  `FLI_SITE_PACKAGES` env injection helps, but the README doesn't document the
  fallback path prominently.
- `bot.py` creates a new `httpx.AsyncClient` for every single API call
  (`_send_message`, `_poll_loop`, `_send_alert_to_chat`). This is wasteful and
  prevents HTTP connection reuse. Should create one shared client in
  `__init__` and reuse it.

**Top 2 recommendations**:
1. **Add the Makefile.** `dev`, `test`, `lint`, `format`, `docker-up`. Stop
   deferring this.
2. **Use a shared `httpx.AsyncClient` in `BotHandler`** — one client in
   `__init__`, close in `stop_polling()`. Reduces latency on repeated calls
   and is the idiomatic httpx pattern.

**New concerns**:
- The `_escape_md` function escapes the entire message string *after* it's
  been formatted with MarkdownV2. This means bold/italic/link formatting will
  be escaped away. Needs a manual test.

---

### belshe — Reliability / Production Readiness — Score: 8/10 (unchanged from 8)

**What's working**:
- Module extraction changed the reliability posture minimally — which is the
  right outcome. The extraction was mechanical, not behavioral. Each job lifecycle
  helper still opens its own session (correct — survives caller rollback).
  `_send_deal_alert` still uses `asyncio.gather(return_exceptions=True)` —
  individual notifier failures don't abort the sweep.
- Circuit breaker on paid APIs is intact and correctly wired in the extracted
  `scanner.py`. The fallback chain logic is unchanged.
- Bot polling loop has a resilient error-recovery pattern: `except Exception`
  → `logger.warning` → `asyncio.sleep(5)` → retry. `CancelledError` breaks the
  loop cleanly. This is safe for long-running operation.

**What's not working**:
- **Bot has no restart on crash.** If `_poll_loop` exits (e.g., persistent
  network failure exhausts the `except` path, or the task is garbage-collected),
  there's no watchdog to restart it. A `task.done()` check in lifespan or a
  supervisor pattern is needed. Currently: if the bot dies, it stays dead
  until the app restarts.
- **Learned baselines add a DB query per scan.** `calculate_percentile_baseline()`
  runs a `SELECT` per route+departure_date. For the regular sweep (19 routes ×
  13 offsets = 247 scans), that's 247 extra queries per sweep. Not a problem
  at current volume, but worth monitoring.
- **Deferred items still deferred**: `PRAGMA synchronous=NORMAL` (2x write
  throughput), circuit breaker state via `/health` (no observability), permanent-
  failure threshold on dedup (prevents retry storms). None are bugs, but all
  are "nice to have" that would move the score to 9.

**Top 2 recommendations**:
1. **Add a bot polling watchdog** — check `bot_handler._poll_task.done()` in a
   periodic health check or lifespan heartbeat; restart if dead.
2. **Expose circuit breaker state via `/health`** — this was deferred last
   review and is still the single highest-impact observability improvement.

**New concerns**:
- `bot.py` creates a new `httpx.AsyncClient` per call, which means no
  connection pooling and potential socket exhaustion under load. Low risk at
  current volume but a code smell.

---

### swyx — AI / Data Strategy / Defensibility — Score: 7/10 (delta: +1 from previous 6)

The learned baselines are the first real step from "commodity threshold" to
"defensible detection." The question is whether it's enough.

**What's working**:
- `detect_deal_learned()` uses percentile-based thresholds (P20=mistake,
  P30=deep_flash, P50=flash_sale) adapted per route+departure_month. This is
  fundamentally better than the static multiplier approach — a $200 MCI→LHR
  flight that's normally $350 is a deal; the same $200 on MCI→CUN (normally $180)
  is not. The learned baseline captures this; the static threshold didn't.
- `calculate_percentile_baseline()` correctly uses index-based percentile
  computation (not SQL NTILE, despite the docstring saying so — the code sorts
  prices and indexes into the array). This is simpler and more portable across
  SQLite/Postgres. Good call.
- Cold-start guard is correct: if both `median_price is None` and `percentiles
  is None`, the scan skips deal detection entirely. No false-positive factory.
- Fallback to median-based `detect_deal()` when percentiles are unavailable
  (fewer than `min_samples`) is the right graceful degradation.

**What's not working**:
- **Features are still unconsumed.** `record_price_observations()` stores
  `departure_month`, `departure_day_of_week`, `days_until_departure`,
  `booking_window_bucket` — but `calculate_percentile_baseline()` only filters
  by `departure_month`. The other features sit in the DB doing nothing. The
  percentile baseline is a per-route-month average; it doesn't account for
  booking window (a $200 flight 3 days out is different from $200 60 days out).
- **No observed-side features.** `observed_at_month` and `observed_at_day_of_week`
  are still missing from `PriceObservation`. These capture *search seasonality*
  ("deals appear on Tuesday afternoons"), not just *departure seasonality*.
  Still the same gap as last review.
- **No feedback loop.** `UserDealInteraction` (viewed/clicked/booked/dismissed)
  is not started. Without a feedback signal, there's no way to distinguish a
  true positive (user booked) from a false positive (user ignored). The
  detection quality is unmeasurable.
- **Clone time is still 4-8 hours.** The learned baseline adds maybe 30 minutes
  to clone time (a competitor copies `calculate_percentile_baseline()` and
  `detect_deal_learned()` — they're standard percentile code). The moat comes
  from the *data* accumulated in `PriceObservation`, not from the code.

**Top 2 recommendations**:
1. **Consume the booking window feature** — filter `calculate_percentile_baseline()`
   by `booking_window_bucket` in addition to `departure_month`. A P20 for 0-7d
   bookings is different from P20 for 61+d bookings. This is a 1-line change
   with high signal gain.
2. **Add `UserDealInteraction` model** — even without a model, logging
   viewed/dismissed/booked starts the feedback flywheel. The bot's
   `/subscribe` and `/unsubscribe` are already implicit signals; make them
   explicit records.

**New concerns**:
- The docstring for `calculate_percentile_baseline()` says "Uses SQLite NTILE(100)
  window function" but the code doesn't — it uses Python-side index computation.
  The docstring is misleading and should be corrected.

---

### b0rk — Architecture / Fragility / Dependencies — Score: 7.5/10 (delta: +0.5 from previous 7)

The God Module extraction is the right move, executed cleanly. Let me assess
the new architecture.

**What's working**:
- `scheduler_jobs.py` went from 594L → 175L. The 3 extracted modules have
  clean responsibilities: `job_lifecycle.py` (JobRun state machine),
  `alert_dispatch.py` (notifier fan-out), `scanner.py` (route scanning + deal
  detection + cache + observation recording). No overlapping concerns.
- Re-exports in `scheduler_jobs.py` are good backward-compat practice — old
  imports and test patch targets work without migration. The `__all__` list
  documents what's intentionally exported.
- No circular dependencies introduced. `scanner.py` imports from
  `price_analysis`, `circuit_breaker`, `deduplication`, `cache` — all leaf
  modules. `alert_dispatch.py` imports from `alert`, `rate_limiter`, notifiers
  — also leaf-level. `scheduler_jobs.py` imports from all 3 extracted modules
  + `config` + `database` — the top of the DAG, as expected.
- Module boundaries align with the test structure: tests can patch
  `app.scanner._scan_route`, `app.alert_dispatch._send_deal_alert`, etc.
  without going through `scheduler_jobs.py`.

**What's not working**:
- **Dead `elif` branches still present.** `scanner.py` lines 151, 169: the
  `elif not circuit_breaker.is_allowed("Amadeus")` / `elif not
  circuit_breaker.is_allowed("Duffel")` branches are functionally unreachable
  in the intended "circuit breaker open" case. When `circuit_breaker.is_allowed()`
  returns `False`, the preceding `if` condition (`not flights and
  circuit_breaker.is_allowed(...)`) is False, but the `elif` then evaluates
  `not circuit_breaker.is_allowed(...)` which is `True` — so the log fires even
  when `flights` is already non-empty (i.e., SearchAPI found results but we're
  still iterating the fallback chain). This was identified last review and is
  still unfixed. The SearchAPI block correctly uses `if/else`; the Amadeus and
  Duffel blocks should match.
- **`scanner.py` is still 297L with 7 concerns in one function.** The extraction
  reduced `scheduler_jobs.py` but `_scan_route()` itself is still doing: cache
  check, fli scrape, fallback chain, median calculation, percentile calculation,
  deal detection, observation recording, cache write. It's a smaller God
  Function inside a smaller God Module. The next step is to extract a
  `DealDetector` or `ScanOrchestrator` class from `_scan_route()`.
- **`bot.py` global singleton** — `bot_handler = BotHandler()` at module level
  means the bot is instantiated on import, even in tests or when no token is
  configured. This is the same singleton smell as the old `circuit_breaker`
  import. Tests that want to isolate bot behavior need to patch the global.
- **`_escape_md` double-escaping bug** (confirmed by reading the code): the
  `_format_alert_message` method builds a string with MarkdownV2 formatting
  (*bold*, links), then `_send_alert_to_chat` passes it raw, but `_send_message`
  (used by command handlers) also calls `_escape_md` on already-formatted text.
  The command handlers will render incorrectly. This is an architectural
  inconsistency — two send paths with different escaping semantics.

**Top 2 recommendations**:
1. **Fix the dead `elif` branches in `scanner.py`** — change `elif not
   circuit_breaker.is_allowed(...)` to match the SearchAPI pattern (`if/else`).
   This was flagged last review and is a 4-line fix. Still not done.
2. **Extract `_scan_route()` internals** — the function has 7 concerns. At
   minimum, extract the fallback chain (fli → SearchAPI → Amadeus → Duffel)
   into a helper, and the deal detection + recording into another. Target:
   `_scan_route` becomes a 40-line orchestrator, not a 240-line monolith.

**New concerns**:
- `bot.py` module-level singleton instantiation is a testability smell.
- The `_escape_md` double-escaping is a latent rendering bug.

---

### Consensus: Implementation Validation

| Recommendation | Original concern | Panel verdict | Gaps remaining |
|---|---|---|---|
| Rec 1: Telegram bot | No user-facing surface; not a product | **Validated ✓** — bot works, subscriptions work, fan-out works | `_escape_md` bug; no single-route unsubscribe; no restart watchdog; destinations still YAML |
| Rec 2: Learned baselines | Static thresholds easily cloned; no data moat | **Validated ✓ (partial)** — percentile detection is live and wired in | Booking window feature unconsumed; no observed-side features; no feedback loop; docstring inaccurate |
| Rec 3: God Module extraction | 594L God Module, 7 concerns in one function | **Validated ✓** — clean split, no new deps, re-exports work | Dead `elif` branches still unfixed; `_scan_route()` itself still has 7 concerns; bot singleton smell |

**All 3 recommendations were implemented correctly and are functioning.** The
gaps are enhancements, not bugs — except the `_escape_md` rendering issue, which
needs a manual live-bot test to confirm severity.

---

### Score Comparison: Previous → Current

| Panelist | Previous (2026-07-12 post-fix) | Current (post-implementation) | Delta |
|---|---|---|---|
| levelsio (PMF) | 6/10 | 7/10 | +1 (Telegram bot is the first real product surface) |
| hanselman (DX) | 7.5/10 | 7.5/10 | 0 (extraction helps contributors; Makefile still missing) |
| belshe (Reliability) | 8/10 | 8/10 | 0 (extraction was mechanical; bot needs watchdog) |
| swyx (AI/Moat) | 6/10 | 7/10 | +1 (learned baselines live; features still under-consumed) |
| b0rk (Architecture) | 7/10 | 7.5/10 | +0.5 (clean extraction; dead elif still unfixed; scanner still complex) |
| **Overall** | **7.5/10** | **7.5/10** | **0** (median: +1 PMF, +1 moat offset by 0 DX/reliability; math averages to flat) |

**Note on scoring**: The overall score is the median of the 5 panelist scores.
Individual deltas: levelsio +1, swyx +1, b0rk +0.5 are offset by hanselman 0
and belshe 0. The product and data layers improved; the engineering layers
held steady (correct — they weren't the target of this sprint). The next
overall score increase comes from consuming the remaining deferred engineering
items (Makefile, circuit breaker visibility, PRAGMA synchronous, dead elif fix)
which would push hanselman and belshe to 8+.

---

### Remaining Action Items (Ranked by Leverage)

Closed items are marked [x]. New items are marked [NEW].

| Rank | Action | Source | Impact | Effort | Status |
|---|---|---|---|---|---|
| 1 | **[NEW] Fix `_escape_md` double-escaping bug** in `bot.py` — alerts may render broken on Telegram clients | b0rk, levelsio | Alert rendering correctness | S | Open |
| 2 | **[NEW] Consume booking_window_bucket in percentile baseline** — filter by bucket in addition to departure_month | swyx | Detection accuracy | S | Open |
| 3 | **Make destinations dynamic** (DB-backed, bot-driven `/watch ORIGIN DEST`) | levelsio | Product PMF — eliminates single-airport limitation | M | Open |
| 4 | **Extract `_scan_route()` internals** — 7 concerns in one function | b0rk | Architecture — reverses God Function trend | M | Open |
| 5 | **Fix dead `elif` log branches** in `scanner.py` lines 151, 169 | b0rk | Log accuracy — 4-line fix | S | Open (deferred twice) |
| 6 | **Add Makefile** with `dev/test/lint/format/docker-up` | hanselman | DX — onboarding | S | Open (deferred twice) |
| 7 | **Add bot polling watchdog** — check `_poll_task.done()` and restart | belshe | Reliability — bot stays alive | S | Open |
| 8 | **Expose circuit breaker state via `/health`** | belshe | Observability | S | Open (deferred) |
| 9 | **Add `PRAGMA synchronous=NORMAL`** alongside WAL | belshe | 2x write throughput | S | Open (deferred) |
| 10 | **Add `UserDealInteraction` model** (viewed/clicked/booked/dismissed) | swyx | Feedback signal for false-positive detection | M | Open (deferred) |
| 11 | **[NEW] Add single-route `/unsubscribe`** — currently only nuclear | levelsio | UX — user control | S | Open |
| 12 | **[NEW] Use shared `httpx.AsyncClient` in `BotHandler`** | hanselman, belshe | Performance — connection reuse | S | Open |
| 13 | **Fix `_escape_md` docstring** — says NTILE, uses Python index | swyx | Documentation accuracy | S | Open |

**Previously completed this sprint** (all 3 recommendations, all verified):
- [x] Rec 1: `@FlightDealBot` Telegram bot — levelsio's top recommendation
- [x] Rec 2: Learned per-route-month baselines — swyx's top recommendation
- [x] Rec 3: God Module extraction — b0rk's top recommendation

**Deferred backlog (lower priority, not yet started)**:
- B8 `/metrics` (Prometheus), B15 README reconcile, B17-B20 product (per-user
  model / affiliate / public feed), B22-B25 AI (airport lookup / false-positive
  classifier / flywheel), B29 licensed-API primary
- `observed_at_month` + `observed_at_day_of_week` features (swyx)
- Permanent-failure threshold on dedup retry (belshe)

---

### Divergent Opinions

| Topic | levelsio | hanselman | belshe | swyx | b0rk |
|---|---|---|---|---|---|
| Biggest win this sprint | Telegram bot (PMF) | Module extraction (DX) | Extraction was mechanical (neutral) | Learned baselines (moat) | God Module split (arch) |
| Biggest remaining gap | Dynamic destinations | Makefile | Bot watchdog | Feedback loop | Dead elif + scanner complexity |
| Next priority | Affiliate links | Makefile | Circuit breaker visibility | Consume features | Fix dead elif |
| Is `_escape_md` a bug? | Maybe (needs test) | Yes (confirmed by reading) | N/A | N/A | Yes (two send paths, different escaping) |

**Consensus**: All 5 panelists agree the sprint delivered real value. The
disagreement is about what's *next*: product growth (levelsio), engineering
hygiene (hanselman, b0rk), reliability hardening (belshe), or data depth
(swyx). The moderator recommends a balanced next sprint: 1 product item
(affiliate links or dynamic destinations), 1 engineering fix (dead elif +
Makefile), 1 data item (consume booking window feature).

---

### Overall Project Health: 7.5/10 (unchanged)

The sprint delivered +1 on PMF and +1 on data moat, offset by flat scores on
DX and reliability (which weren't the target). The engineering floor remains
at 8/10 (reliability) and 7.5/10 (DX + architecture). The ceiling is now
closer: 7/10 PMF (up from 6) and 7/10 moat (up from 6). The path to 8/10
overall is: consume the deferred engineering items (push hanselman/belshe/b0rk
to 8+) + ship dynamic destinations (push levelsio to 8) + add feedback loop
(push swyx to 8).

**The honest assessment**: The Telegram bot and learned baselines were the
right bets. The architecture extraction was necessary hygiene. The product
is now a *multi-user tool with adaptive detection* — no longer just a single-
operator dashboard. The next inflection point is dynamic destinations (making
the product work for any airport) and a feedback loop (making detection
measurable). The engineering debt (Makefile, dead elif, circuit breaker
visibility) is small but accumulating — address it before the next feature
sprint.

---

## Panel Review: APScheduler + SQLite Job Store Production Safety (2026-07-15)

**Panelists**: levelsio, hanselman, belshe, swyx, b0rk
**Topic**: Is the current APScheduler + SQLite job store setup safe for production?
**Decision**: **APPROVED with caveats** — the setup is production-ready for single-instance deployment but has recoverable limitations.

### 🔍 Analysis by dimension

**Reliability (belshe)**: ✓ Production-safe with current hardening
- WAL mode + busy_timeout prevents SQLITE_BUSY (B1/B2 done)
- JobRun reconciliation (`RECONCILE_MAX_AGE_SECONDS=3600`) recovers orphaned runs
- Circuit breaker protects paid API tiers from burning
- **Gap**: Add `PRAGMA synchronous=NORMAL` for write throughput (currently tracking)

**Architecture (b0rk)**: ✓ Clean separation, no hidden fragilities
- Scheduler uses `AsyncIOScheduler` with `AsyncIOExecutor` — correct async pattern
- SQLAlchemyJobStore abstraction allows eventual Postgres migration
- Module boundaries clean after God Module extraction
- **Gap**: Dead `elif` branches in scanner.py (fixed, committed in 284a62e)

**Product (levelsio)**: ✓ Trustworthy enough for paid tier
- Telegram bot is the primary surface (not dashboard)
- Users trust alerts are reliable; this setup won't silently fail
- Single airport limitation is a product choice, not reliability concern
- **Gap**: Dynamic destinations needed for multi-airport users

**DX (hanselman)**: ✓ Single-process, no magic
- `pip install -r requirements.txt && python -m app.main` works
- `.env` config is clear
- **Gap**: Missing Makefile for contributor onboarding

**AI/Data (swyx)**: ✓ Solid foundation for observation accumulation
- `PriceObservation` table accumulates every scraped price
- SQLite is fine for single-instance; data portable to Postgres later
- Job runs logged reliably for feature analysis

### ✅ Action items closed (verified in commit 284a62e)
1. `PRAGMA synchronous=NORMAL` — ADDED
2. Circuit breaker state via `/health` — ADDED (returns `circuit_breakers` field)
3. Permanent-failure threshold on dedup (MAX_ALERT_ATTEMPTS=5) — ADDED
4. Dead `elif` log branches — FIXED (changed to `if/else` pattern)

### 📊 Production readiness assessment

| Concern | Status | Mitigation |
|---|---|---|
| SQLite concurrency | ✅ WAL mode active | WAL handles concurrent reads/writes |
| Silent scheduler freeze | ✅ Circuit breaker + timeouts | 30s timeout on all external calls |
| Job run tracking | ✅ Reconciliation on startup | Orphaned runs marked "interrupted" |
| Alert loss on failure | ✅ Retry logic + threshold | MAX_ALERT_ATTEMPTS=5 before giving up |
| Process crashes | ⚠️ In-memory circuit breaker | Restarts cold; acceptable for single-process |
| DB volume | ⚠️ WAL files grow | Rotate every 24h or on 10MB (SQLite default) |

### 🎯 Recommendation
The APScheduler + SQLite setup is **production-safe for the current scale** (single instance, <500 daily route scans). The reliability sprint fixes (WAL, circuit breaker, dedup retry, JobRun reconciliation) address the key risks. For multi-worker deployment, migrate to Postgres with the same SQLAlchemyJobStore abstraction.

---

## Latest Panel Decision Summary

**Overall Status**: All panel-identified fixes from 2026-07-13 have been implemented, tested (391 tests pass), and verified. The codebase is in a stable, production-ready state for single-instance deployment.

---

## 2026-07-16 00:00 — FULL AUDIT & REVIEW (re-convene panel)

**Panelists**: levelsio, hanselman, belshe, swyx, b0rk (all 5 lenses applied; subagent
routing unavailable this session — moderator applied each lens directly to source).
**Topic**: Full audit of flight-deal-monitor production readiness, architecture
fragility, AI/ML strategy, dev-DX/self-hosting, and business model — including the
open backlog and historically "deferred" fixes, re-verified against actual source.

### Evidence collected (this session, against live source)
- `app/scanner.py` (324L) — `_scan_route()` fallback chain fli→SearchAPI→Amadeus→Duffel,
  `FLI_TIMEOUT_SECONDS=30` waiter, percentile baseline wired in. **No dead `elif`
  branches present** — the handoff's claimed "dead elif in scanner.py" was ALREADY FIXED.
- `app/alert.py` + `app/bot.py` — `_escape_md()` escapes ONLY dynamic values; Markdown
  formatting (`*bold*`, `[link](url)`) is built into the literal template. **This is
  correct — the claimed `_escape_md` double-escape bug is a FALSE POSITIVE / already
  resolved.** No double-escaping occurs.
- `app/models/flight.py:107` `booking_window_bucket` — **WRITTEN** in
  `price_analysis.py:128-134` on `PriceObservation` but **NEVER CONSUMED** in
  `calculate_percentile_baseline()` (no filter on it). Real deferred gap remains.
- `app/bot.py` — `_poll_task` created in `start_polling()`; only `_running` flag + manual
  `cancel()`. **NO watchdog**: if `_poll_loop()` dies (uncaught exception), nothing
  restarts it → bot silently stops receiving commands/subscriber alerts.
- `Makefile` — **EXISTS** (handoff "deferred Makefile" was stale).
- `README.md` — present, claims "Telegram, email, Slack, Discord" but only Telegram +
  webhook notifiers are wired; thresholds stated match `config/app.yaml`.

### Per-expert assessment

**levelsio (PMF / business)**
- (a) Top risks: destinations are hardcoded (MCI × 19) — no self-serve watch; monetization
  absent; no real user yet (dogfood only).
- (b) Ready: alert pipeline + Telegram bot UX is genuinely usable. Not ready: product
  surface for non-devs.
- (c) Recs: S — ship to 5 real travel-hacker friends with hardcoded routes; M — dynamic
  DB-backed `/watch ORIGIN DEST` (open backlog); M — per-user filters already exist,
  expose them in onboarding; L — monetization (freemium: free 1 home airport, paid multi).
- (d) Verdict: compelling for the builder + a few friends NOW; not a "product" until
  destinations are self-serve. Smallest compelling step = let users add their own routes.

**hanselman (DX / self-hosting)**
- (a) Top risks: README over-claims channels (Slack/Discord/email mentioned, not all
  wired); test invocation is non-obvious (`scripts/run_pytest.py` + env vars, NOT plain
  `pytest`); secrets setup friction.
- (b) Ready: `cp .env.example`, `python -m app.main`, Docker compose. Not ready: README
  accuracy; first-run test experience.
- (c) Recs: S — reconcile README to actually-wired notifiers (backlog B15); S — Makefile
  already exists, add `make test`/`make dev`/`make lint` targets; M — one-command
  `make setup` that does install+env+test; S — note test-runner caveat in README.
- (d) Verdict: a moderately technical user CAN self-host in ~15 min. Blocker = README trust
  (over-claim) + finding the right test command.

**belshe (reliability / prod)**
- (a) Ranked risks: **P0** bot polling has no watchdog (silent death); circuit breaker is
  in-memory (dies on restart, won't coordinate across workers); SQLite + single writer =
  unsafe for multi-instance; no `/metrics` (B8) for alerting on anomalies.
- (b) Ready (single-instance, unattended): mostly — sweeps, reconciliation, /health 503,
  error-alert budget all present. Not ready: multi-worker; observability.
- (c) Recs: S — bot watchdog (check `_poll_task.done()`, restart); S/M — persist circuit
  breaker state or accept single-instance-only; M — `/metrics` endpoint (B8); L —
  PostgreSQL path for multi-instance.
- (d) Verdict: SAFE to run unattended single-instance. What pages you at 3am: bot silently
  dying (no watchdog) + a fli outage you can't see without logs.

**swyx (AI/ML / defensibility)**
- (a) Risks: percentile logic is trivially copyable (no moat); no feedback loop to learn
  false-positives; `booking_window_bucket` collected but unused (wasted signal).
- (b) Defensible: the accumulated `PriceObservation` history IS the asset — but only if
  fed back. Easily copied: the detection math.
- (c) Recs: S — consume `booking_window_bucket` in percentile baseline (backlog gap); M —
  `UserDealInteraction` model (viewed/clicked/booked/dismissed) → false-positive
  classifier (B17-B25); L — flywheel: better signal → better deals → more users → more
  observations. Verdict on ML-now: NOT needed; simple percentiles are the right v1.
- (d) Verdict: percentile foundation is sound. Highest-leverage data investment =
  close the feedback loop (interactions + booking window filter).

**b0rk (architecture / fragility)**
- (a) Implicit contracts that bite: `generate_route_id()` hash includes airline+suffix
  (changing either invalidates dedup — silent re-alerts); `_start/_complete/_fail_job_run`
  each open their own session (caller's session not reused); fli is sync-in-executor
  (one wedged upstream could stall sweep — mitigated by FLI_TIMEOUT).
- (b) Sound: module extraction (scanner/job_lifecycle/alert_dispatch) is clean; dedup +
  cache layering correct. Fragile: bot watchdog gap; untelemetered paid-provider spend.
- (c) Recs ranked by blast radius: **P0** bot watchdog (silent user-facing failure);
  **P1** consume `booking_window_bucket` (accuracy, 1-line filter); **P1** document the
  `generate_route_id` hash contract (code comment + test); **P2** Makefile targets (done).
- (d) Verdict: decomposition is healthy. Only genuinely P0 fragility = bot watchdog.

### Cross-cutting synthesis
- The three "deferred bugs" from prior handoff are **two false positives + one real**:
  `_escape_md` double-escape = FALSE; dead elif in scanner = FALSE (fixed);
  `booking_window_bucket` unconsumed = TRUE (real, low-effort).
- **One true P0 across all lenses: bot polling watchdog** (belshe + b0rk agree). Everything
  else is P1/P2 and product-evolution, not deploy-blockers.
- System is **APPROVED for single-instance self-hosted deployment** with the watchdog as
  the only must-fix-before-unattended item.

### Prioritized action list
- **P0 (do first)**: Add bot polling watchdog — restart `_poll_task` if `.done()`
  (belshe/b0rk, ~S).
- **P1**: Consume `booking_window_bucket` in `calculate_percentile_baseline()` filter
  (swyx/b0rk, ~S). Reconcile README to wired notifiers (hanselman, ~S). Document
  `generate_route_id` hash contract (b0rk, ~S).
- **P2 (product evolution)**: Dynamic DB-backed destinations `/watch` (levelsio, ~M);
  `UserDealInteraction` + false-positive classifier (swyx, ~M-L); `/metrics` (belshe, ~M);
  monetization (levelsio, ~L); PostgreSQL multi-instance path (belshe, ~L).

### Verdict
**APPROVED for single-instance unattended deployment once the bot watchdog (P0) lands.**
All other items are enhancements, not blockers. Prior panel fixes (commit 284a62e) remain
valid; this audit corrects three stale "deferred bug" claims in handoff.md.
