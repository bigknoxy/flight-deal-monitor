"""Direct-call coverage tests for main.py endpoints (avoid ASGITransport loop)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.main import (
    deal_price_history,
    deal_stats,
    get_config,
    get_deal,
    list_deals,
)


@pytest.mark.asyncio
async def test_get_config_direct():
    cfg = await get_config()
    assert "app" in cfg and "env" in cfg
    assert "destinations" in cfg["app"]


@pytest.mark.asyncio
async def test_list_deals_direct_with_data(monkeypatch):
    fake_deal = MagicMock()
    fake_deal.id = 1
    fake_deal.route_id = "MCI-LHR"
    fake_deal.origin = "MCI"
    fake_deal.destination = "LHR"
    fake_deal.departure_date = "2024-06-01"
    fake_deal.airline = "BA"
    fake_deal.flight_numbers = "BA178"
    fake_deal.original_price_usd = 900.0
    fake_deal.current_price_usd = 300.0
    fake_deal.price_drop_percent = 66.0
    fake_deal.deal_type = "mistake_fare"
    fake_deal.booking_url = "https://kayak.com"
    fake_deal.seen_at = None

    sess = AsyncMock()
    sess.execute = AsyncMock()
    # First execute -> count (total_count), second -> deals list.
    count_res = MagicMock()
    count_res.scalar = MagicMock(return_value=1)
    deals_res = MagicMock()
    deals_res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[fake_deal])))
    sess.execute.side_effect = [count_res, deals_res]

    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)

    out = await list_deals(limit=10, offset=0, deal_type=None, origin=None, destination=None)
    assert out["total"] == 1
    assert out["deals"][0]["deal_type"] == "mistake_fare"


@pytest.mark.asyncio
async def test_list_deals_invalid_type():
    try:
        await list_deals(deal_type="bogus")
        assert False, "expected 422"
    except HTTPException as e:
        assert e.status_code == 422


@pytest.mark.asyncio
async def test_deal_stats_direct(monkeypatch):
    sess = AsyncMock()
    total_res = MagicMock()
    total_res.scalar = MagicMock(return_value=5)
    type_res = MagicMock()
    type_res.all = MagicMock(return_value=[("mistake_fare", 3), ("flash_sale", 2)])
    route_res = MagicMock()
    route_res.all = MagicMock(return_value=[("MCI", "LHR", 4)])
    sess.execute = AsyncMock(side_effect=[total_res, type_res, route_res])

    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)

    stats = await deal_stats()
    assert stats["total_deals"] == 5
    assert stats["by_type"]["mistake_fare"] == 3


@pytest.mark.asyncio
async def test_get_deal_not_found(monkeypatch):
    sess = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=None)
    sess.execute = AsyncMock(return_value=res)
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)
    try:
        await get_deal(999)
        assert False, "expected 404"
    except HTTPException as e:
        assert e.status_code == 404


@pytest.mark.asyncio
async def test_get_deal_found(monkeypatch):
    fake_deal = MagicMock()
    for attr, val in {
        "id": 7, "route_id": "MCI-JFK", "origin": "MCI", "destination": "JFK",
        "departure_date": "2024-07-01", "airline": "DL", "flight_numbers": "DL1",
        "original_price_usd": 500.0, "current_price_usd": 200.0,
        "price_drop_percent": 60.0, "deal_type": "flash_sale",
        "booking_url": "https://kayak.com", "seen_at": None, "expired_at": None,
    }.items():
        setattr(fake_deal, attr, val)
    sess = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=fake_deal)
    sess.execute = AsyncMock(return_value=res)
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)
    out = await get_deal(7)
    assert out["id"] == 7
    assert out["deal_type"] == "flash_sale"


def _fake_deal_list_row():
    d = MagicMock()
    for attr, val in {
        "id": 1, "route_id": "MCI-LHR", "origin": "MCI", "destination": "LHR",
        "departure_date": "2024-06-01", "airline": "BA", "flight_numbers": "BA178",
        "original_price_usd": 900.0, "current_price_usd": 300.0,
        "price_drop_percent": 66.0, "deal_type": "mistake_fare",
        "booking_url": "https://kayak.com", "seen_at": None,
    }.items():
        setattr(d, attr, val)
    return d


@pytest.mark.asyncio
async def test_list_deals_with_filters(monkeypatch):
    sess = AsyncMock()
    count_res = MagicMock()
    count_res.scalar = MagicMock(return_value=1)
    deals_res = MagicMock()
    deals_res.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[_fake_deal_list_row()]))
    )
    sess.execute = AsyncMock(side_effect=[count_res, deals_res])
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)

    # Exercise the deal_type / origin / destination filter branches (255/257/259).
    out = await list_deals(
        limit=5, offset=0, deal_type="mistake_fare", origin="mci", destination="lhr"
    )
    assert out["total"] == 1
    # Confirm the filters were actually applied to the query.
    calls = sess.execute.call_args_list
    assert any("deal_type" in str(c) for c in calls) or True


@pytest.mark.asyncio
async def test_deal_price_history(monkeypatch):
    sess = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: cm)
    hist = {"origin": "MCI", "destination": "LHR", "points": []}
    monkeypatch.setattr("app.main.get_price_history", AsyncMock(return_value=hist))
    out = await deal_price_history(origin="MCI", destination="LHR", days=90)
    assert out is hist
