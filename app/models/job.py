"""Job models for scheduler."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class ScheduledJob(SQLModel, table=True):
    """Scheduled job model for tracking APScheduler jobs."""

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True, description="APScheduler job ID")
    job_type: str = Field(description="'regular_sweep' or 'mistake_sweep'")
    last_run: Optional[datetime] = Field(default=None, description="Last execution time")
    next_run: Optional[datetime] = Field(default=None, description="Next scheduled run")
    status: str = Field(default="active", description="'active', 'paused', or 'failed'")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JobRun(SQLModel, table=True):
    """Job run model for tracking individual job executions."""

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True, description="APScheduler job ID")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    duration_seconds: Optional[float] = Field(default=None)
    status: str = Field(default="running", description="'running', 'success', 'failed'")
    error_message: Optional[str] = Field(default=None)
    deals_detected: int = Field(default=0, description="Number of deals detected")
    alerts_sent: int = Field(default=0, description="Number of alerts sent")