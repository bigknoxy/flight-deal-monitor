"""Amadeus API client for flight search and pricing."""

import logging
from typing import List, Optional

import httpx

from app.config import config

logger = logging.getLogger(__name__)


class AmadeusClient:
    """Amadeus API client."""

    def __init__(self):
        self.client_id = config.env.amadeus_client_id
        self.client_secret = config.env.amadeus_client_secret
        self.env = config.env.amadeus_env
        self.base_url = (
            "https://api.amadeus.com/v2"
            if self.env == "production"
            else "https://test.api.amadeus.com/v2"
        )
        self.token: Optional[str] = None
        self.token_expires_at: Optional[float] = None

    async def _get_token(self) -> str:
        """Get OAuth token from Amadeus."""
        if self.token and self.token_expires_at:
            import time

            if time.time() < self.token_expires_at - 60:  # 1 min buffer
                return self.token

        url = f"{self.base_url}/security/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            result = response.json()

        self.token = result["access_token"]
        import time

        self.token_expires_at = time.time() + result["expires_in"]
        logger.info("Obtained new Amadeus access token")
        return self.token

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        max_results: int = 10,
    ) -> List[dict]:
        """Search for flights using Amadeus API."""
        url = f"{self.base_url}/shopping/flight-offers"
        headers = {"Authorization": f"Bearer {await self._get_token()}"}
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": 1,
            "max": max_results,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            result = response.json()

        flights = result.get("data", [])
        logger.info(f"Found {len(flights)} flights from {origin} to {destination}")
        return flights

    async def get_flight_price(self, flight_offer: dict) -> float:
        """Extract price from flight offer."""
        try:
            price = float(flight_offer["price"]["total"])
            return price
        except (KeyError, TypeError, ValueError):
            logger.warning(f"Could not extract price from flight offer: {flight_offer}")
            return 0.0