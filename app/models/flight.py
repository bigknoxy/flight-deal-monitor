"""Flight deal models."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class FlightDeal(SQLModel, table=True):
    """Flight deal model for tracking detected deals."""

    id: Optional[int] = Field(default=None, primary_key=True)
    route_id: str = Field(index=True, description="Unique route identifier")
    origin: str = Field(description="Origin airport code")
    destination: str = Field(description="Destination airport code")
    departure_date: str = Field(description="Departure date (YYYY-MM-DD)")
    airline: str = Field(description="Airline name")
    flight_numbers: str = Field(description="Flight numbers (comma-separated)")
    original_price_usd: float = Field(description="Original price before deal")
    current_price_usd: float = Field(description="Current deal price")
    price_drop_percent: float = Field(description="Percentage price drop")
    deal_type: str = Field(
        description="Type of deal: 'flash_sale' or 'mistake_fare'"
    )
    booking_url: str = Field(description="Booking URL")
    seen_at: datetime = Field(default_factory=datetime.utcnow)
    expired_at: Optional[datetime] = Field(default=None, description="24h after seen_at")


class AlertHistory(SQLModel, table=True):
    """Alert history model for tracking sent alerts."""

    id: Optional[int] = Field(default=None, primary_key=True)
    flight_deal_id: int = Field(foreign_key="flightdeal.id", description="Related flight deal")
    sent_at: datetime = Field(default_factory=datetime.utcnow, description="When alert was sent")
    telegram_message_id: Optional[str] = Field(default=None, description="Telegram message ID")
    status: str = Field(description="'sent' or 'failed'")
    error_message: Optional[str] = Field(default=None, description="Error if failed")


class ScheduledJob(SQLModel, table=True):
    """Scheduled job model for tracking APScheduler jobs."""

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(description="APScheduler job ID")
    job_type: str = Field(description="'regular_sweep' or 'mistake_sweep'")
    last_run: Optional[datetime] = Field(default=None, description="Last execution time")
    next_run: Optional[datetime] = Field(default=None, description="Next scheduled run")
    status: str = Field(description="'active', 'paused', or 'failed'")