"""Authentication routes for login, register, and logout."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.hash import bcrypt
from sqlalchemy import select

from app.auth import create_session
from app.config import config
from app.database import AsyncSessionLocal
from app.models.user import User
from app.templates import render

router = APIRouter()


def _registration_open() -> bool:
    """Registration is open unless explicitly disabled via env."""
    return not config.env.registration_disabled


def _login_redirect(user_id: int) -> RedirectResponse:
    token = create_session(user_id)
    response = RedirectResponse(url="/dashboard", status_code=303)
    # Only mark the session cookie secure when behind HTTPS (e.g. a TLS
    # reverse proxy). Local/plain-HTTP dev stays usable.
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        max_age=86400 * 7,
        secure=config.env.session_secure,
        samesite="lax",
    )
    return response


@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Render the login page."""
    return render(request, "auth/login.html", error=None)


@router.post("/auth/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
) -> HTMLResponse:
    """Validate credentials and set session cookie."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if not user or not bcrypt.verify(password, user.password_hash):
        return render(
            request,
            "auth/login.html",
            error="Invalid email or password.",
        )

    return _login_redirect(user.id)


@router.get("/auth/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    """Render the registration page."""
    if not _registration_open():
        return RedirectResponse(url="/auth/login", status_code=303)
    return render(request, "auth/register.html", error=None)


@router.post("/auth/register", response_class=HTMLResponse)
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
) -> HTMLResponse:
    """Create a new user and auto-login."""
    if not _registration_open():
        return RedirectResponse(url="/auth/login", status_code=303)

    if not email or "@" not in email:
        return render(
            request,
            "auth/register.html",
            error="Please provide a valid email address.",
        )

    if len(password) < 6:
        return render(
            request,
            "auth/register.html",
            error="Password must be at least 6 characters.",
        )

    password_hash = bcrypt.hash(password)
    user = User(email=email, password_hash=password_hash)

    async with AsyncSessionLocal() as session:
        # Check if email already taken
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            return render(
                request,
                "auth/register.html",
                error="An account with this email already exists.",
            )

        session.add(user)
        await session.commit()
        await session.refresh(user)

    return _login_redirect(user.id)


@router.post("/auth/logout", response_class=HTMLResponse)
async def logout() -> RedirectResponse:
    """Clear the session cookie and redirect to login."""
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.set_cookie(key="session", value="", httponly=True, max_age=0)
    return response
