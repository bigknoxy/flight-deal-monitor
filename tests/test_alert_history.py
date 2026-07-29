"""Direct-call coverage tests for alert history endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.main import get_alert, get_alert_history


def _fake_deal():
    d = MagicMock()
    for attr, val in {
        "id": 1,
        "route_id": "MCI-LHR",
        "origin": "MCI",
        "destination": "LHR",
        "departure_date": "2024-06-01",
        "airline": "BA",
        "flight_numbers": "BA178",
        "original_price_usd": 900.0,
        "current_price_usd": 300.0,
        "price_drop_percent": 66.0,
        "deal_type": "mistake_fare",
        "booking_url": "https://kayak.com",
        "seen_at": datetime(2024, 5, 1, 12, 0, 0),
        "expired_at": datetime(2024, 5, 2, 12, 0, 0),
    }.items():
        setattr(d, attr, val)
    return d


def _fake_alert():
    a = MagicMock()
    for attr, val in {
        "id": 1,
        "flight_deal_id": 1,
        "sent_at": datetime(2024, 6, 1, 12, 0, 0),
        "telegram_message_id": "12345",
        "status": "sent",
        "error_message": None,
    }.items():
        setattr(a, attr, val)
    return a


def _fake_failed_alert():
    a = MagicMock()
    for attr, val in {
        "id": 2,
        "flight_deal_id": 1,
        "sent_at": datetime(2024, 6, 2, 12, 0, 0),
        "telegram_message_id": None,
        "status": "failed",
        "error_message": "Telegram API error",
    }.items():
        setattr(a, attr, val)
    return a


def _make_session(count_result, rows_result):
    """Build a mock AsyncSessionLocal context manager."""
    sess = AsyncMock()
    sess.execute = AsyncMock(side_effect=[count_result, rows_result])
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    return sess, cm


@pytest.mark.asyncio
async def test_get_alert_history_default(monkeypatch):
    """Test getting alert history with default parameters."""
    count_res = MagicMock()
    count_res.scalar = MagicMock(return_value=2)
    rows_res = MagicMock()
    rows_res.all = MagicMock(return_value=[(_fake_alert(), _fake_deal()), (_fake_failed_alert(), _fake_deal())])
    sess, cm = _make_session(count_res, rows_res)
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)

    out = await get_alert_history(
        limit=50, offset=0, start_date=None, end_date=None, deal_type=None
    )
    assert out["total"] == 2
    assert out["limit"] == 50
    assert out["offset"] == 0
    assert len(out["alerts"]) == 2
    assert out["alerts"][0]["id"] == 1
    assert out["alerts"][0]["flight_deal"]["id"] == 1
    assert out["alerts"][0]["flight_deal"]["origin"] == "MCI"
    assert out["alerts"][0]["status"] == "sent"
    assert out["alerts"][1]["status"] == "failed"
    assert out["alerts"][1]["error_message"] == "Telegram API error"


@pytest.mark.asyncio
async def test_get_alert_history_invalid_deal_type():
    """Test that invalid deal_type returns 422."""
    try:
        await get_alert_history(
            limit=50, offset=0, start_date=None, end_date=None, deal_type="bogus"
        )
        assert False, "expected 422"
    except HTTPException as e:
        assert e.status_code == 422
        assert "Invalid deal_type" in e.detail


@pytest.mark.asyncio
async def test_get_alert_history_invalid_start_date():
    """Test that invalid start_date returns 422."""
    try:
        await get_alert_history(
            limit=50, offset=0, start_date="not-a-date", end_date=None, deal_type=None
        )
        assert False, "expected 422"
    except HTTPException as e:
        assert e.status_code == 422
        assert "Invalid start_date" in e.detail


@pytest.mark.asyncio
async def test_get_alert_history_invalid_end_date():
    """Test that invalid end_date returns 422."""
    try:
        await get_alert_history(
            limit=50, offset=0, start_date=None, end_date="not-a-date", deal_type=None
        )
        assert False, "expected 422"
    except HTTPException as e:
        assert e.status_code == 422
        assert "Invalid end_date" in e.detail


@pytest.mark.asyncio
async def test_get_alert_history_empty(monkeypatch):
    """Test alert history with no results."""
    count_res = MagicMock()
    count_res.scalar = MagicMock(return_value=0)
    rows_res = MagicMock()
    rows_res.all = MagicMock(return_value=[])
    sess, cm = _make_session(count_res, rows_res)
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)

    out = await get_alert_history(
        limit=50, offset=0, start_date=None, end_date=None, deal_type=None
    )
    assert out["total"] == 0
    assert out["alerts"] == []


@pytest.mark.asyncio
async def test_get_alert_history_with_deal_type_filter(monkeypatch):
    """Test filtering by deal_type."""
    count_res = MagicMock()
    count_res.scalar = MagicMock(return_value=1)
    rows_res = MagicMock()
    rows_res.all = MagicMock(return_value=[(_fake_alert(), _fake_deal())])
    sess, cm = _make_session(count_res, rows_res)
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)

    out = await get_alert_history(
        limit=50, offset=0, start_date=None, end_date=None, deal_type="mistake_fare"
    )
    assert out["total"] == 1
    assert out["alerts"][0]["flight_deal"]["deal_type"] == "mistake_fare"


@pytest.mark.asyncio
async def test_get_alert_not_found(monkeypatch):
    """Test getting a non-existent alert returns 404."""
    sess = AsyncMock()
    res = MagicMock()
    res.first = MagicMock(return_value=None)
    sess.execute = AsyncMock(return_value=res)
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)

    try:
        await get_alert(999)
        assert False, "expected 404"
    except HTTPException as e:
        assert e.status_code == 404
        assert "not found" in e.detail.lower()


@pytest.mark.asyncio
async def test_get_alert_found(monkeypatch):
    """Test getting an alert by ID."""
    sess = AsyncMock()
    res = MagicMock()
    res.first = MagicMock(return_value=(_fake_alert(), _fake_deal()))
    sess.execute = AsyncMock(return_value=res)
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)

    out = await get_alert(1)
    assert out["id"] == 1
    assert out["flight_deal_id"] == 1
    assert out["status"] == "sent"
    assert out["telegram_message_id"] == "12345"
    assert out["flight_deal"]["id"] == 1
    assert out["flight_deal"]["origin"] == "MCI"
    assert out["flight_deal"]["destination"] == "LHR"
    assert out["flight_deal"]["deal_type"] == "mistake_fare"
    assert out["flight_deal"]["booking_url"] == "https://kayak.com"


@pytest.mark.asyncio
async def test_get_alert_failed_status(monkeypatch):
    """Test getting an alert with failed status."""
    sess = AsyncMock()
    res = MagicMock()
    res.first = MagicMock(return_value=(_fake_failed_alert(), _fake_deal()))
    sess.execute = AsyncMock(return_value=res)
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)

    out = await get_alert(2)
    assert out["id"] == 2
    assert out["status"] == "failed"
    assert out["error_message"] == "Telegram API error"
    assert out["telegram_message_id"] is None
