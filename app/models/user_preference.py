"""User preference model for personalization."""

from sqlmodel import Field, SQLModel


class UserPreference(SQLModel, table=True):
    """User preference model for storing per-user settings."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    key: str
    value: str
