"""Flight deal models."""

from datetime import datetime

from sqlmodel import Field, SQLModel


class FlightDeal(SQLModel, table=True):
    """Flight deal model for tracking detected deals."""

    id: int | None = Field(default=None, primary_key=True)
    route_id: str = Field(index=True, description="Unique route identifier")
    origin: str = Field(description="Origin airport code")
    destination: str = Field(description="Destination airport code")
    departure_date: str = Field(description="Departure date (YYYY-MM-DD)")
    airline: str = Field(description="Airline name")
    flight_numbers: str = Field(description="Flight numbers (comma-separated)")
    original_price_usd: float = Field(description="Original price before deal")
    current_price_usd: float = Field(description="Current deal price")
    price_drop_percent: float = Field(description="Percentage price drop")
    deal_type: str = Field(description="Type of deal: 'flash_sale' or 'mistake_fare'")
    booking_url: str = Field(description="Booking URL")
    seen_at: datetime = Field(default_factory=datetime.utcnow)
    expired_at: datetime | None = Field(
        default=None, description="24h after seen_at"
    )
    trip_type: str = Field(
        default="one_way",
        description="Discriminator: 'one_way' or 'round_trip'. Keeps baseline/dedup keys separate.",
    )

    # Tier-2 round-trip enrichment (populated only when round_trip_enrichment
    # is enabled and a confirmed one-way deal is enriched). Never used as a
    # deal-detection input; always surfaced with its provenance source.
    round_trip_price_usd: float | None = Field(
        default=None, description="Real or derived round-trip price (USD)"
    )
    rt_source: str | None = Field(
        default=None,
        description="Provenance: 'SearchAPI'/'Amadeus'/'Duffel' or 'derived_quota'/'derived_error'",
    )
    rt_return_date: str | None = Field(
        default=None, description="Return date used for the RT lookup (provenance)"
    )
    rt_is_phantom: bool = Field(
        default=False,
        description="True when RT per-leg cost is below the one-way price (suspicious deal)",
    )


class AlertHistory(SQLModel, table=True):
    """Alert history model for tracking sent alerts."""

    id: int | None = Field(default=None, primary_key=True)
    flight_deal_id: int = Field(
        foreign_key="flightdeal.id", description="Related flight deal"
    )
    sent_at: datetime = Field(
        default_factory=datetime.utcnow, description="When alert was sent"
    )
    telegram_message_id: str | None = Field(
        default=None, description="Telegram message ID"
    )
    status: str = Field(description="'sent' or 'failed'")
    error_message: str | None = Field(default=None, description="Error if failed")


class PriceObservation(SQLModel, table=True):
    """Every scraped price point, accumulated to build a real market baseline.

    Unlike ``FlightDeal`` (only flagged deals), this table stores ALL scanned
    prices so ``calculate_median_price`` can derive a baseline from history
    instead of from the current batch's cheapest flight (which caused
    first-scan false positives).
    """

    __tablename__ = "price_observations"

    id: int | None = Field(default=None, primary_key=True)
    origin: str = Field(index=True, description="Origin airport code")
    destination: str = Field(index=True, description="Destination airport code")
    departure_date: str = Field(index=True, description="Departure date (YYYY-MM-DD)")
    airline: str = Field(default="", description="Airline name")
    price_usd: float = Field(description="Scraped price in USD")
    observed_at: datetime = Field(
        default_factory=datetime.utcnow, index=True, description="When scraped"
    )
    trip_type: str = Field(
        default="one_way",
        description="Discriminator: 'one_way' or 'round_trip'. Scopes median baseline.",
    )

    # Pre-computed ML features (populated at write time so future models
    # don't need expensive backfills). All nullable for backward compat.
    days_until_departure: int | None = Field(
        default=None,
        description="Days between observed_at and departure_date",
    )
    departure_month: int | None = Field(
        default=None,
        description="Month of departure (1-12) — seasonal signal",
    )
    departure_day_of_week: int | None = Field(
        default=None,
        description="Day of week of departure (0=Mon .. 6=Sun)",
    )
    booking_window_bucket: str | None = Field(
        default=None,
        description="0-7d, 8-21d, 22-60d, 61+d",
    )
