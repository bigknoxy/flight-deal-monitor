"""Integration tests for percentile-baseline booking-window scoping.

Uses a real in-memory SQLite engine so the booking_window_bucket filter
actually executes against stored rows (the unit tests mock the session).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.models.flight import PriceObservation
from app.utils.price_analysis import (
    calculate_percentile_baseline,
    record_price_observations,
)


def _make_engine():
    return create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.mark.asyncio
async def test_baseline_scoped_by_booking_window():
    """A long-window observation must NOT leak into a near-term baseline.

    Seeds MCI->LHR month=6 with an expensive '61+d' row and a cheap '0-7d'
    row, then asserts the bucketed baseline ignores the expensive one.
    """
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine) as session:
        session.add_all(
            [
                PriceObservation(
                    origin="MCI", destination="LHR", departure_date="2024-06-10",
                    airline="AA", price_usd=900, departure_month=6,
                    booking_window_bucket="61+d",
                ),
                PriceObservation(
                    origin="MCI", destination="LHR", departure_date="2024-06-10",
                    airline="BA", price_usd=950, departure_month=6,
                    booking_window_bucket="61+d",
                ),
                PriceObservation(
                    origin="MCI", destination="LHR", departure_date="2024-06-10",
                    airline="UA", price_usd=300, departure_month=6,
                    booking_window_bucket="0-7d",
                ),
            ]
        )
        await session.commit()

        # No bucket -> all three rows inform the baseline (P50 ~ 900).
        wide = await calculate_percentile_baseline(
            session, "MCI", "LHR", "2024-06-10", min_samples=1
        )
        assert wide is not None
        assert wide[50] >= 900, f"expected long-window P50, got {wide[50]}"

        # Near-term bucket -> only the 0-7d row (price 300) is in scope.
        scoped = await calculate_percentile_baseline(
            session, "MCI", "LHR", "2024-06-10",
            min_samples=1, booking_window_bucket="0-7d",
        )
        assert scoped is not None
        assert scoped[50] == 300, f"bucketed P50 should be 300, got {scoped[50]}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_record_price_observations_writes_bucket():
    """record_price_observations persists the computed booking_window_bucket."""
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    flights = [{"validatingAirlineCodes": ["AA"], "price": {"total": "300.00"}}]
    async with AsyncSession(engine) as session:
        n = await record_price_observations(
            session, "MCI", "LHR", "2024-06-01", flights
        )
        assert n == 1
        rows = (
            await session.execute(
                __import__("sqlalchemy").select(PriceObservation)
            )
        ).scalars().all()
        assert rows[0].booking_window_bucket is not None

    await engine.dispose()
