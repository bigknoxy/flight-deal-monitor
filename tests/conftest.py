import pytest

from app.models.flight import FlightDeal


@pytest.fixture
def make_deal():
    def _make_deal(**kwargs):
        defaults = dict(
            route_id="test_route",
            origin="MCI",
            destination="LHR",
            departure_date="2024-06-01",
            airline="BA",
            flight_numbers="BA123",
            original_price_usd=500.0,
            current_price_usd=150.0,
            price_drop_percent=70.0,
            deal_type="mistake_fare",
            booking_url="https://example.com/book",
        )
        defaults.update(kwargs)
        return FlightDeal(**defaults)
    return _make_deal
