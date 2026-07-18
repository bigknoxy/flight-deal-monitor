"""Configuration management using Pydantic Settings."""

import logging
import os

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Sentinel default that must never reach production. Sessions are signed with
# this key, so leaving it unchanged lets anyone forge an admin cookie.
DEFAULT_SECRET_KEY = "change-me-in-production"

# Single source of truth for the booking-link provider name. Booking URLs are
# built in app.scanner._build_booking_url and the name is surfaced in the
# dashboard UI; both must stay in sync, so the label lives here.
BOOKING_PROVIDER_NAME = "Kayak"


class DealThresholds(BaseSettings):
    """Deal detection thresholds."""

    mistake_fare_percent: float = 0.70
    flash_sale_percent: float = 0.50
    deep_flash_percent: float = 0.65


class RouteMultipliers(BaseSettings):
    """Route volatility multipliers."""

    domestic: float = 1.0
    transatlantic: float = 0.8
    transpacific: float = 0.7
    latin_america: float = 1.2
    europe: float = 0.85


class LongWeekendConfig(BaseSettings):
    """Long weekend deal monitoring configuration."""

    enabled: bool = False
    interval_minutes: int = 60
    look_ahead_months: int = 12


class FlexibleDatesConfig(BaseSettings):
    """Flexible date range search configuration."""

    enabled: bool = False
    range_days: int = 3


class MultiCityConfig(BaseSettings):
    """Multi-city route search configuration."""

    enabled: bool = False
    max_stops: int = 2


class AppConfig(BaseSettings):
    """Application configuration from YAML file."""

    name: str = "flight-deal-monitor"
    version: str = "1.0.0"

    home_airports: list[str] = Field(default_factory=lambda: ["MCI"])
    destinations: list[str] = Field(
        default_factory=lambda: [
            "JFK",
            "LGA",
            "EWR",
            "BOS",
            "PWM",
            "ONT",
            "SBA",
            "PLS",
            "SJO",
            "AUS",
            "DUB",
            "BCN",
            "LTN",
            "EDI",
            "OSL",
            "TYO",
            "ICN",
        ]
    )

    deal_thresholds: DealThresholds = DealThresholds()
    route_multipliers: RouteMultipliers = RouteMultipliers()
    long_weekend: LongWeekendConfig = LongWeekendConfig()
    flexible_dates: FlexibleDatesConfig = FlexibleDatesConfig()
    multi_city: MultiCityConfig = MultiCityConfig()

    max_results_per_route: int = 10
    look_ahead_days: int = 90
    look_back_days: int = 30

    min_price_usd: int = 100
    max_alerts_per_hour: int = 10

    # Minimum number of accumulated price observations required before a route
    # is considered to have a real baseline. Below this, scans are cold-start
    # and emit no alerts (prevents first-scan false positives).
    min_baseline_samples: int = 5

    regular_sweep_interval: int = 1800
    mistake_sweep_interval: int = 900
    job_coalesce: bool = True

    cache_ttl_minutes: int = 360

    # When fli (the free source) errors, fall back to paid providers.
    # Disabled by default to avoid burning paid quota on transient fli hiccups;
    # only genuine emptiness (no results) is considered a real miss.
    fallback_on_fli_error: bool = False

    fli_site_packages: str = ""

    # Tier-2 round-trip enrichment: when enabled, a confirmed one-way deal
    # triggers exactly ONE lazy paid round-trip lookup (never during the free
    # sweep). Off by default so the monitor stays $0 until the operator opts in.
    round_trip_enrichment: bool = False
    max_rt_lookups_per_hour: int = 20
    rt_cache_ttl_hours: int = 24
    rt_return_offset_days: int = 3

    secret_key: str = "change-me-in-production"

    @classmethod
    def from_yaml(cls, path: str = "config/app.yaml") -> "AppConfig":
        """Load configuration from YAML file."""
        if not os.path.exists(path):
            return cls()

        with open(path) as f:
            config_data = yaml.safe_load(f)

        if config_data is None:
            return cls()

        return cls(**config_data.get("app", {}))


class EnvConfig(BaseSettings):
    """Environment configuration from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Amadeus API
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_env: str = "test"  # "test" or "production"

    # Duffel API
    duffel_api_token: str = ""

    # SearchAPI
    searchapi_api_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Email (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    email_from: str = ""
    email_to: str = ""

    # Slack (optional)
    slack_webhook_url: str = ""

    # Discord (optional)
    discord_webhook_url: str = ""

    # Database
    # Default path lives under ./data so a volume-mounted directory
    # (e.g. docker-compose ./data:/app/data) survives container recreation.
    database_url: str = "sqlite:///./data/flight_deals.db"

    # Registration / bootstrap
    registration_disabled: bool = False
    admin_email: str = ""
    admin_password: str = ""

    # Logging
    log_level: str = "INFO"

    # Session cookie security. Set SESSION_SECURE=true when the app is served
    # behind HTTPS (e.g. a TLS reverse proxy). Local/plain-HTTP dev stays usable.
    session_secure: bool = False

    # Signing key for session cookies. MUST be set via .env (SECRET_KEY) in any
    # real deployment — the AppConfig yaml default is a known constant and lets
    # anyone forge a session. Preferred over the yaml value when provided.
    secret_key: str = ""

    @field_validator("amadeus_env")
    @classmethod
    def validate_amadeus_env(cls, v: str) -> str:
        """Validate Amadeus environment."""
        if v not in ["test", "production"]:
            raise ValueError("amadeus_env must be 'test' or 'production'")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()


class Config:
    """Combined configuration."""

    def __init__(self, app_config_path: str = "config/app.yaml"):
        self.app = AppConfig.from_yaml(app_config_path)
        self.env = EnvConfig()

        # An explicit SECRET_KEY in .env wins over the yaml default. Without it
        # we keep the (insecure) yaml value but scream, because a default key
        # means session cookies are forgeable.
        if self.env.secret_key:
            self.app.secret_key = self.env.secret_key

        if self.app.secret_key == DEFAULT_SECRET_KEY:
            logger.error(
                "SECURITY: SECRET_KEY is the insecure default "
                f"'{DEFAULT_SECRET_KEY}'. Set SECRET_KEY in your .env file or an "
                "attacker can forge session cookies. Sessions are NOT safe until "
                "this is changed."
            )
        elif self.env.secret_key:
            logger.info("SECRET_KEY loaded from environment (.env).")


# Global config instance
config = Config()
