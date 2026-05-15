"""Database models."""

from app.models.flight import FlightDeal, AlertHistory
from app.models.job import ScheduledJob, JobRun

__all__ = [
    "FlightDeal",
    "AlertHistory",
    "ScheduledJob",
    "JobRun",
]