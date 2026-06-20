"""Configuration management using Pydantic Settings."""

import os
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
from typing import Dict, List


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


class AppConfig(BaseSettings):
    """Application configuration from YAML file."""

    name: str = "flight-deal-monitor"
    version: str = "1.0.0"

    home_airports: List[str] = Field(default_factory=lambda: ["MCI"])
    destinations: List[str] = Field(
        default_factory=lambda: ["JFK", "LGA", "EWR", "BOS", "PWM", "ONT", "SBA", "PLS", "SJO", "AUS",
                                  "DUB", "BCN", "LTN", "EDI", "OSL", "TYO", "ICN"]
    )

    deal_thresholds: DealThresholds = DealThresholds()
    route_multipliers: RouteMultipliers = RouteMultipliers()

    max_results_per_route: int = 10
    look_ahead_days: int = 90
    look_back_days: int = 30

    min_price_usd: int = 100
    max_alerts_per_hour: int = 10

    regular_sweep_interval: int = 1800
    mistake_sweep_interval: int = 900
    job_coalesce: bool = True

    cache_ttl_minutes: int = 360
    cache_variance_threshold: float = 0.05

    @classmethod
    def from_yaml(cls, path: str = "config/app.yaml") -> "AppConfig":
        """Load configuration from YAML file."""
        if not os.path.exists(path):
            return cls()

        with open(path, "r") as f:
            config_data = yaml.safe_load(f)

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

    # Database
    database_url: str = "sqlite:///./flight_deals.db"

    # Logging
    log_level: str = "INFO"

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


# Global config instance
config = Config()