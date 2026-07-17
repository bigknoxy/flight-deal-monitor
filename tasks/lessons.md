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

---

## Lesson 5: fli subprocess crashes on non-serializable + None price

**Failure mode**: `app/scrapers/fli_client.py` printed `json.dumps(result)` from a
fli subprocess. fli returns `arrival_airport` as an `Airport` **enum** (not str),
so `json.dumps` raised `TypeError` and the subprocess died → every free search
failed → fell through to paid providers (no keys) → **zero deals / empty dashboard**.
Separately, `f"{result.price:.2f}"` raised `NoneType.__format__` when a result had
`price=None`, killing whole-route conversion.

**Detection signal**: `/deals` returns 0 deals but scheduler "runs"; subprocess
exit non-zero in logs; UI empty despite healthy server.

**Prevention rule**:
- Pass `default=_json_default` to `json.dumps` (`_json_default` coerces `Enum`→`.value`).
- Guard `price = result.price if result.price is not None else 0.0`.
- Wrap per-result conversion in try/except so one bad result can't sink a route.
- TDD these paths (enum arrival_airport, None price, zero price) — see
  `tests/test_fli_client.py::TestFLIClientJsonDefault` + `TestFLIClientToDict`.

**Reference**: `app/scanner.py::_scan_route` consumes fli via `run_in_executor`.

---

## Lesson 6: Google Flights deep links are dead — use Kayak

**Failure mode**: Booking links built with Google `?q=` (or path `/flights/MCI-JFK/...`
or hand-rolled `tfs=` protobuf) now 302 → `/unsupported`. Google deprecated ALL
structured deep-linking in 2026. Even the user's own historical `tfs=` example link
now redirects to `/unsupported`. Booking link showed wrong/empty destination+date.

**Detection signal**: Book link opens Google "unsupported" page; destination/date
not pre-filled.

**Prevention rule**: Build booking links with **Kayak** path format
`https://www.kayak.com/flights/{ORIG}-{DEST}/{departure}` (RT appends `/{return}`).
Verified 200 + pre-fills fields. Skyscanner path format hits captcha (avoid).
`booking_url` is a **persisted column** on `FlightDeal` — fixing the builder only
helps future scans; backfill existing rows after a URL-format change.

**Reference**: `app/scanner.py::_build_booking_url`; backfill via async
`AsyncSessionLocal` (sync Session fails on the async engine).
