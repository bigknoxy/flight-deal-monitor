"""Database models."""

from app.models.flight import AlertHistory, FlightDeal
from app.models.job import JobRun

__all__ = [
    "FlightDeal",
    "AlertHistory",
    "JobRun",
]
