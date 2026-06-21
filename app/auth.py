"""Authentication middleware using signed session cookies."""

from fastapi import HTTPException, Request
from itsdangerous import URLSafeTimedSerializer

from app.config import config

serializer = URLSafeTimedSerializer(config.app.secret_key, salt="auth")


def create_session(user_id: int) -> str:
    """Create a signed session token for the given user ID."""
    return serializer.dumps({"user_id": user_id})


def verify_session(token: str) -> dict | None:
    """Verify a session token and return its payload, or None if invalid/expired."""
    try:
        return serializer.loads(token, max_age=86400 * 7)
    except Exception:
        return None


async def get_current_user(request: Request) -> dict | None:
    """Extract the current user from the request's session cookie."""
    token = request.cookies.get("session")
    if not token:
        return None
    return verify_session(token)


async def require_login(request: Request) -> dict:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user
