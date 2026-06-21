"""User model for authentication."""

from datetime import datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """User model for authentication and personalization."""

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = Field(default="user")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
