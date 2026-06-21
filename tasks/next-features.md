# Next Features & Polish Options

## New Features
- **Mobile push notifications** (Firebase/APNs via ntfy.sh)
- **Price prediction ML** (linear regression on price history, "buy now" signal)
- **Browser extension** (Chrome/Firefox — one-click add route from any airline page)
- **Price alerts via SMS** (Twilio or email-to-SMS gateways)
- **Multi-user support** (team/shared deal boards)
- **Export deals** (CSV, JSON, iCal for calendar)
- **Price drop RSS feed** (for feed readers)

## Polish
- **Dashboard charts** (price history line chart via Chart.js, deal type pie chart)
- **Dark/light toggle** (persisted in localStorage)
- **Pagination UX** (infinite scroll with loading spinner, page size selector)
- **Toast notifications** (HTMX SSE for real-time deal alerts in dashboard)
- **Responsive improvements** (table horizontal scroll on mobile, collapsible sidebar)
- **Keyboard shortcuts** (g+d → deals, g+r → routes, g+h → history)
- **Confirmation dialogs** (before removing route, Alpine.js modal)

## Infra
- **Docker Compose** with PostgreSQL + pgAdmin
- **Health monitoring** (uptime-kuma, healthchecks.io pings)
- **Backup strategy** (daily SQLite dump to S3/Backblaze)
- **Prometheus metrics** endpoint for Grafana dashboards
- **Rate limiting** per-IP on auth endpoints
