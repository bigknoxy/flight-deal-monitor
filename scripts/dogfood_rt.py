import os
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)

os.environ["DATABASE_URL"] = "sqlite:////dev/shm/dogfood_rt.db"

import asyncio
import logging

logging.basicConfig(level=logging.INFO, force=True)
print("importing app modules...", flush=True)
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.templating import Jinja2Templates

from app.database import AsyncSessionLocal, init_db
from app.models.flight import FlightDeal
from app.round_trip import enrich_round_trip

templates = Jinja2Templates(directory=str(Path("app/templates").resolve()))


async def scenario(name, deal_kwargs, patch_rt=True, quota=True, rt_price="371.00"):
    fake_flight = {
        "price": {"total": rt_price},
        "validatingAirlineCodes": ["AA"],
        "itineraries": [{"segments": []}],
    }

    class FakeProvider:
        def __init__(self):
            pass

        async def search_flights(self, *a, **k):
            return [fake_flight]

        def get_flight_price(self, f):
            return float(f["price"]["total"])

    patchers = [patch("app.round_trip.acquire_rt_slot", return_value=quota)]
    if patch_rt:
        # RT_PROVIDER_ORDER holds class references, so patch the list itself.
        patchers.append(
            patch("app.round_trip.RT_PROVIDER_ORDER", [FakeProvider])
        )
    for p in patchers:
        p.start()
    try:
        async with AsyncSessionLocal() as session:
            deal = FlightDeal(**deal_kwargs)
            session.add(deal)
            await session.commit()
            await session.refresh(deal)
            await enrich_round_trip(deal, session)
            await session.commit()
            html = templates.get_template("partials/deal_row.html").render(
                deal=deal, request=None
            )
            rt_lines = [
                l.strip()
                for l in html.splitlines()
                if "RT $" in l or "one-way" in l.lower() or "RT ·" in l
            ]
            print(f"\n=== {name} ===", flush=True)
            print("  round_trip_price_usd:", deal.round_trip_price_usd, flush=True)
            print("  rt_source:", deal.rt_source, flush=True)
            print("  rt_is_phantom:", deal.rt_is_phantom, flush=True)
            print("  UI lines:", rt_lines[:3], flush=True)
    finally:
        for p in patchers:
            p.stop()


async def main():
    print("calling init_db...", flush=True)
    await init_db()
    print("init_db done.", flush=True)
    base = dict(
        route_id="dogfood-1",
        origin="MCI",
        destination="ONT",
        departure_date="2026-08-29",
        airline="Frontier",
        flight_numbers="F9",
        original_price_usd=400.0,
        current_price_usd=259.0,
        price_drop_percent=35.0,
        deal_type="flash_sale",
        booking_url="https://www.google.com/travel/flights",
        trip_type="one_way",
    )
    # Real RT path (provider returns $371)
    await scenario("REAL RT (SearchAPI returns $371)", base)
    # Derived fallback path (quota exhausted -> 2x estimate)
    await scenario(
        "DERIVED (quota exhausted)", {**base, "route_id": "dogfood-2"}, quota=False
    )
    print("\nDOGFOOD DONE")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("FATAL:", repr(e), flush=True)
        raise
