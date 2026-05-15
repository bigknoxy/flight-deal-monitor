"""Prometheus metrics for Flight Deal Monitor.

Exposes counters and histograms for monitoring:
- API calls per provider (Amadeus, Duffel)
- Telegram alerts sent
- Deals detected (by type)
- Job durations
- Error rates (by component)
"""

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# API calls per provider
# ---------------------------------------------------------------------------
api_calls_total = Counter(
    "api_calls_total",
    "Total API calls made to flight providers",
    ["provider"],
)

# Convenience constants for label values
PROVIDER_AMADEUS = "amadeus"
PROVIDER_DUFFEL = "duffel"

# ---------------------------------------------------------------------------
# Telegram alerts
# ---------------------------------------------------------------------------
telegram_alerts_sent_total = Counter(
    "telegram_alerts_sent_total",
    "Total Telegram alert messages sent",
)

telegram_alerts_failed_total = Counter(
    "telegram_alerts_failed_total",
    "Total Telegram alert messages that failed to send",
)

# ---------------------------------------------------------------------------
# Deals detected
# ---------------------------------------------------------------------------
deals_detected_total = Counter(
    "deals_detected_total",
    "Total flight deals detected",
    ["deal_type"],
)

# Label values matching model deal_type values
DEAL_TYPE_FLASH_SALE = "flash_sale"
DEAL_TYPE_MISTAKE_FARE = "mistake_fare"

# ---------------------------------------------------------------------------
# Job durations
# ---------------------------------------------------------------------------
job_duration_seconds = Histogram(
    "job_duration_seconds",
    "Duration of scheduled jobs in seconds",
    ["job_id"],
    buckets=(5, 10, 30, 60, 120, 300, 600, 1800, 3600),
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
errors_total = Counter(
    "errors_total",
    "Total errors encountered",
    ["component"],
)

# Component label values
COMPONENT_AMADEUS = "amadeus"
COMPONENT_DUFFEL = "duffel"
COMPONENT_TELEGRAM = "telegram"
COMPONENT_SCHEDULER = "scheduler"
COMPONENT_DATABASE = "database"
COMPONENT_APP = "app"


def metrics_output() -> tuple[bytes, str]:
    """Generate the latest Prometheus metrics output.

    Returns:
        Tuple of (metrics_bytes, content_type) for HTTP response.
    """
    return generate_latest(), CONTENT_TYPE_LATEST
