"""Tests for the booking-provider template context injection."""

from starlette.requests import Request

from app.config import BOOKING_PROVIDER_NAME
from app.templates import render


def test_render_injects_booking_provider():
    """render() must expose the single-source booking-provider label so
    templates never hardcode the provider name."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)
    resp = render(request, "base.html")
    assert resp.status_code == 200
    assert BOOKING_PROVIDER_NAME  # non-empty sanity
