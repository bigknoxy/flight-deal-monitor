"""Job models for scheduler."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ScheduledJob(SQLModel, table=True):
    """Scheduled job model for tracking APScheduler jobs."""

    __table_args__ = {"extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(index=True, description="APScheduler job ID")
    job_type: str = Field(description="'regular_sweep' or 'mistake_sweep'")
    last_run: datetime | None = Field(default=None, description="Last execution time")
    next_run: datetime | None = Field(default=None, description="Next scheduled run")
    status: str = Field(default="active", description="'active', 'paused', or 'failed'")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobRun(SQLModel, table=True):
    """Job run model for tracking individual job executions."""

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(index=True, description="APScheduler job ID")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = Field(default=None)
    duration_seconds: float | None = Field(default=None)
    status: str = Field(default="running", description="'running', 'success', 'failed'")
    error_message: str | None = Field(default=None)
    deals_detected: int = Field(default=0, description="Number of deals detected")
    alerts_sent: int = Field(default=0, description="Number of alerts sent")
