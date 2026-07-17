"""Telegram subscription model."""

from datetime import datetime

from sqlmodel import Field, SQLModel


class TelegramSubscription(SQLModel, table=True):
    """Telegram subscription for interactive bot users."""

    id: int | None = Field(default=None, primary_key=True)
    chat_id: str = Field(index=True, description="Telegram chat ID")
    origin: str | None = Field(default=None, description="Filter by origin (None = all)")
    destination: str | None = Field(default=None, description="Filter by destination (None = all)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)
