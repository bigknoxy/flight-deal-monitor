"""Database models."""

from app.models.flight import AlertHistory, FlightDeal
from app.models.job import JobRun
from app.models.user import User
from app.models.user_preference import UserPreference

__all__ = [
    "FlightDeal",
    "AlertHistory",
    "JobRun",
    "User",
    "UserPreference",
]
