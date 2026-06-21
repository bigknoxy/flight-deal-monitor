"""Job models for scheduler."""

from datetime import datetime

from sqlmodel import Field, SQLModel


class JobRun(SQLModel, table=True):
    """Job run model for tracking individual job executions."""

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(index=True, description="APScheduler job ID")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = Field(default=None)
    duration_seconds: float | None = Field(default=None)
    status: str = Field(default="running", description="'running', 'success', 'failed'")
    error_message: str | None = Field(default=None)
    deals_detected: int = Field(default=0, description="Number of deals detected")
    alerts_sent: int = Field(default=0, description="Number of alerts sent")
