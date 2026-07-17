"""Tests for the startup schema-migration guard (ensure_schema)."""
import os
import tempfile

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import ensure_schema


@pytest.mark.asyncio
async def test_ensure_schema_adds_missing_columns():
    """An existing prod DB missing the Tier-1/Tier-2 columns gets them added."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = tmp.name
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")

    # Simulate an OLD schema: flightdeal + price_observations without trip_type
    # and without the Tier-2 FlightDeal columns.
    async with engine.begin() as conn:

        def _create(c):
            c.exec_driver_sql(
                "CREATE TABLE flightdeal ("
                "id INTEGER PRIMARY KEY, route_id VARCHAR, origin VARCHAR, "
                "destination VARCHAR, departure_date VARCHAR, airline VARCHAR, "
                "flight_numbers VARCHAR, original_price_usd FLOAT, "
                "current_price_usd FLOAT, price_drop_percent FLOAT, "
                "deal_type VARCHAR, booking_url VARCHAR, seen_at TIMESTAMP, "
                "expired_at TIMESTAMP)"
            )
            c.exec_driver_sql(
                "CREATE TABLE price_observations ("
                "id INTEGER PRIMARY KEY, origin VARCHAR, destination VARCHAR, "
                "departure_date VARCHAR, airline VARCHAR, price_usd FLOAT, "
                "observed_at TIMESTAMP)"
            )

        await conn.run_sync(_create)

    import app.database as db

    old_engine = db.engine
    db.engine = engine
    try:
        await ensure_schema()

        async with engine.connect() as conn:

            def _cols(c):
                return {r["name"] for r in sa_inspect(c).get_columns("flightdeal")}

            fd_cols = await conn.run_sync(_cols)

            def _po_cols(c):
                return {
                    r["name"] for r in sa_inspect(c).get_columns("price_observations")
                }

            po_cols = await conn.run_sync(_po_cols)
    finally:
        db.engine = old_engine
        await engine.dispose()
        os.unlink(path)

    for col in (
        "trip_type",
        "round_trip_price_usd",
        "rt_source",
        "rt_return_date",
        "rt_is_phantom",
    ):
        assert col in fd_cols, f"flightdeal missing column {col}"
    assert "trip_type" in po_cols, "price_observations missing trip_type"
