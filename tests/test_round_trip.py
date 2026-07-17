"""Tier-2 round-trip enrichment tests.

Round-trip enrichment is OFF by default and only fires (behind
``config.app.round_trip_enrichment``) on a confirmed one-way deal. These tests
verify: flag gating, single paid call + storage, quota/error/timeout fallbacks
to a derived estimate, RT observations are tagged round_trip (never polluting
the one-way baseline), cache hit, phantom suppression, return_date wiring in
the paid clients, and the UI rendering.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import config
from app.models.flight import FlightDeal
from app.round_trip import enrich_round_trip
from app.utils.price_analysis import calculate_median_price


@pytest.fixture(autouse=True)
def _reset_rt_state():
    from app.round_trip import rt_cache

    rt_cache.clear()
    yield


def _make_deal(current_price_usd: float = 259.0) -> FlightDeal:
    return FlightDeal(
        route_id="MCI-ONT-2026-08-29-Frontier",
        origin="MCI",
        destination="ONT",
        departure_date="2026-08-29",
        airline="Frontier",
        flight_numbers="F1",
        original_price_usd=128.0,
        current_price_usd=current_price_usd,
        price_drop_percent=-50.0,
        deal_type="flash_sale",
        booking_url="https://example.com",
        trip_type="one_way",
    )


@pytest.mark.asyncio
async def test_flag_off_no_paid_call():
    config.app.round_trip_enrichment = False
    deal = _make_deal()
    session = AsyncMock()
    with patch("app.round_trip.SearchAPIClient") as mock_cls:
        await enrich_round_trip(deal, session)
    assert deal.round_trip_price_usd is None
    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_flag_on_one_rt_call_and_stored():
    config.app.round_trip_enrichment = True
    deal = _make_deal()
    session = AsyncMock()
    mock_client = MagicMock()
    mock_client.search_flights = AsyncMock(
        return_value=[{"price": {"total": "400.00"}}]
    )
    mock_client.get_flight_price.return_value = 400.0
    with patch(
        "app.round_trip.RT_PROVIDER_ORDER", [MagicMock(return_value=mock_client)]
    ):
        await enrich_round_trip(deal, session)
    assert deal.round_trip_price_usd == 400.0
    assert deal.rt_source  # non-empty provenance tag
    mock_client.search_flights.assert_awaited_once()
    args, _ = mock_client.search_flights.call_args
    assert args[4] is not None  # return_date is the 5th positional arg
    config.app.round_trip_enrichment = False


@pytest.mark.asyncio
async def test_quota_exhausted_uses_derived():
    config.app.round_trip_enrichment = True
    deal = _make_deal()
    session = AsyncMock()
    with patch("app.round_trip.acquire_rt_slot", return_value=False):
        await enrich_round_trip(deal, session)
    assert deal.round_trip_price_usd == pytest.approx(deal.current_price_usd * 2)
    assert deal.rt_source == "derived_quota"
    config.app.round_trip_enrichment = False


@pytest.mark.asyncio
async def test_timeout_uses_derived():
    config.app.round_trip_enrichment = True
    deal = _make_deal()
    session = AsyncMock()

    async def boom(*_a, **_k):
        raise TimeoutError()

    mock_client = MagicMock()
    mock_client.search_flights = boom
    with patch(
        "app.round_trip.RT_PROVIDER_ORDER", [MagicMock(return_value=mock_client)]
    ):
        await enrich_round_trip(deal, session)
    assert deal.rt_source == "derived_error"
    assert deal.round_trip_price_usd == pytest.approx(deal.current_price_usd * 2)
    config.app.round_trip_enrichment = False


@pytest.mark.asyncio
async def test_rt_observations_round_trip_trip_type():
    config.app.round_trip_enrichment = True
    deal = _make_deal()
    session = AsyncMock()
    mock_client = MagicMock()
    mock_client.search_flights = AsyncMock(
        return_value=[{"price": {"total": "400.00"}}]
    )
    mock_client.get_flight_price.return_value = 400.0
    with patch(
        "app.round_trip.RT_PROVIDER_ORDER", [MagicMock(return_value=mock_client)]
    ), patch(
        "app.round_trip.record_price_observations", new=AsyncMock()
    ) as rec:
        await enrich_round_trip(deal, session)
    rec.assert_awaited_once()
    _, kwargs = rec.call_args
    assert kwargs.get("trip_type") == "round_trip"
    config.app.round_trip_enrichment = False


@pytest.mark.asyncio
async def test_rt_excluded_from_one_way_median():
    config.app.round_trip_enrichment = True
    session = AsyncMock()
    captured: dict = {}

    async def fake_execute(q):
        captured["sql"] = str(q)
        res = MagicMock()
        res.all.return_value = [(100.0,), (120.0,)]
        return res

    session.execute = fake_execute
    median = await calculate_median_price(
        session, "MCI", "ONT", min_samples=1, trip_type="one_way"
    )
    assert median == 110.0
    assert "trip_type" in captured["sql"]
    config.app.round_trip_enrichment = False


@pytest.mark.asyncio
async def test_cache_hit_no_second_call():
    config.app.round_trip_enrichment = True
    deal = _make_deal()
    session = AsyncMock()
    mock_client = MagicMock()
    mock_client.search_flights = AsyncMock(
        return_value=[{"price": {"total": "400.00"}}]
    )
    mock_client.get_flight_price.return_value = 400.0
    with patch(
        "app.round_trip.RT_PROVIDER_ORDER", [MagicMock(return_value=mock_client)]
    ):
        await enrich_round_trip(deal, session)
        mock_client.search_flights.reset_mock()
        await enrich_round_trip(deal, session)
    mock_client.search_flights.assert_not_called()
    config.app.round_trip_enrichment = False


@pytest.mark.asyncio
async def test_phantom_deal_flagged():
    config.app.round_trip_enrichment = True
    deal = _make_deal(current_price_usd=259.0)
    session = AsyncMock()
    mock_client = MagicMock()
    # RT total 300 -> per leg 150 < 259 one-way -> phantom
    mock_client.search_flights = AsyncMock(
        return_value=[{"price": {"total": "300.00"}}]
    )
    mock_client.get_flight_price.return_value = 300.0
    with patch(
        "app.round_trip.RT_PROVIDER_ORDER", [MagicMock(return_value=mock_client)]
    ):
        await enrich_round_trip(deal, session)
    assert deal.rt_is_phantom is True
    config.app.round_trip_enrichment = False


@pytest.mark.asyncio
async def test_searchapi_round_trip_param():
    from app.api.searchapi import SearchAPIClient

    client = SearchAPIClient()
    client.api_key = "k"
    captured: dict = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"best_flights": []}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            captured["params"] = params
            return FakeResp()

    with patch("app.api.searchapi.httpx.AsyncClient", FakeClient):
        await client.search_flights("MCI", "ONT", "2026-08-29", return_date="2026-09-01")
    assert captured["params"]["flight_type"] == "round_trip"
    assert captured["params"]["return_date"] == "2026-09-01"


@pytest.mark.asyncio
async def test_amadeus_round_trip_param():
    from app.api.amadeus import AmadeusClient

    client = AmadeusClient()
    captured: dict = {}

    class FakeTokenResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "t", "expires_in": 3600}

    class FakeOffersResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": []}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data=None):
            return FakeTokenResp()

        async def get(self, url, headers=None, params=None):
            if "flight-offers" in url:
                captured["params"] = params
            return FakeOffersResp()

    with patch("app.api.amadeus.httpx.AsyncClient", FakeClient):
        await client.search_flights("MCI", "ONT", "2026-08-29", return_date="2026-09-01")
    assert captured["params"]["returnDate"] == "2026-09-01"


@pytest.mark.asyncio
async def test_duffel_round_trip_param():
    from app.api.duffel import DuffelClient

    client = DuffelClient()
    captured: dict = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"id": "x", "offers": {"data": []}}}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return FakeResp()

        async def post(self, url, headers=None, json=None):
            captured["json"] = json
            return FakeResp()

    with patch("app.api.duffel.httpx.AsyncClient", FakeClient):
        await client.search_flights("MCI", "ONT", "2026-08-29", return_date="2026-09-01")
    slices = captured["json"]["data"]["slices"]
    assert len(slices) == 2
    assert slices[1]["origin"] == "ONT" and slices[1]["destination"] == "MCI"


def test_ui_shows_rt_when_present():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(),
    )
    t = env.get_template("partials/deal_row.html")
    deal = _make_deal()
    deal.round_trip_price_usd = 400.0
    deal.rt_source = "SearchAPI"
    out = t.render(deal=deal)
    assert "RT" in out
    assert "SearchAPI" in out
    assert "one-way" in out

    deal2 = _make_deal()
    deal2.round_trip_price_usd = None
    out2 = t.render(deal=deal2)
    assert "1-way · RT on Kayak" in out2
