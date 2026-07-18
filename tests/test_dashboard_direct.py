"""Direct-call tests for dashboard helper functions.

These call the sync/async helper coroutines directly (not through the HTTP
transport) so coverage's tracer records the bodies. Route add/remove handlers
that mutate config/app.yaml are intentionally not exercised here.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import dashboard as dash


def test_get_route_config():
    cfg = dash._get_route_config()
    assert "home_airports" in cfg
    assert "destinations" in cfg
    assert "long_weekend" in cfg


@pytest.mark.asyncio
async def test_get_deals_empty(monkeypatch):
    sess = AsyncMock()
    count_res = MagicMock()
    count_res.scalar = MagicMock(return_value=0)
    deals_res = MagicMock()
    deals_res.all = MagicMock(return_value=[])
    sess.execute = AsyncMock(side_effect=[count_res, deals_res])
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr(dash, "AsyncSessionLocal", lambda: cm)

    out = await dash._get_deals()
    assert out["total"] == 0
    assert out["deals"] == []


@pytest.mark.asyncio
async def test_get_deals_with_data_and_filters(monkeypatch):
    row = MagicMock()
    for attr, val in {
        "first_id": 3, "origin": "MCI", "destination": "LHR",
        "departure_date": "2024-06-01", "airline": "BA",
        "flight_numbers": "BA178", "original_price": 900.0,
        "cheapest_price": 300.0, "max_drop": 66.0,
        "deal_type": "mistake_fare", "booking_url": "https://kayak.com",
        "seen_at": None, "option_count": 2,
    }.items():
        setattr(row, attr, val)

    sess = AsyncMock()
    count_res = MagicMock()
    count_res.scalar = MagicMock(return_value=1)
    deals_res = MagicMock()
    deals_res.all = MagicMock(return_value=[row])
    sess.execute = AsyncMock(side_effect=[count_res, deals_res])
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr(dash, "AsyncSessionLocal", lambda: cm)

    # Exercise the deal_type / origin / destination filter branches.
    out = await dash._get_deals(
        deal_type="mistake_fare", origin="mci", destination="lhr"
    )
    assert out["total"] == 1
    deal = out["deals"][0]
    assert deal["route_id"] == "MCI-LHR-2024-06-01-BA"
    assert deal["current_price_usd"] == 300.0
    assert deal["option_count"] == 2


@pytest.mark.asyncio
async def test_get_deal_stats(monkeypatch):
    sess = AsyncMock()
    total_res = MagicMock()
    total_res.scalar = MagicMock(return_value=4)
    type_res = MagicMock()
    type_res.all = MagicMock(return_value=[("mistake_fare", 4)])
    route_res = MagicMock()
    route_res.all = MagicMock(return_value=[("MCI", "LHR", 4)])
    sess.execute = AsyncMock(side_effect=[total_res, type_res, route_res])
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    monkeypatch.setattr(dash, "AsyncSessionLocal", lambda: cm)

    stats = await dash._get_deal_stats()
    assert stats["total_deals"] == 4
    assert stats["by_type"]["mistake_fare"] == 4
    assert stats["top_routes"][0]["count"] == 4


@pytest.mark.asyncio
async def test_get_config_display_masks_secrets(monkeypatch):
    monkeypatch.setattr(
        dash.config.env, "telegram_bot_token", "super-secret-token"
    )
    monkeypatch.setattr(dash.config.env, "smtp_user", "user@x.com")
    display = await dash._get_config_display()
    assert display["env"]["telegram_bot_token"] == "****"
    assert display["env"]["smtp_user"] == "****"
    assert display["env"]["amadeus_env"] == dash.config.env.amadeus_env
    assert "route_multipliers" in display["app"]
