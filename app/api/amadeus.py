"""Amadeus API client for flight search and pricing."""

import logging
import time
from typing import Dict, List, Optional

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

 def get_booking_url(self, flight_offer: dict) -> str:
 """Extract booking/deeplink URL from Amadeus flight offer.

 Amadeus Flight Offers Search API returns booking links in two places:
 1. ``flight_offer["links"]["self"]`` — API self-link (not a booking URL)
 2. ``flight_offer["price"]["bookingTickatable"]`` — indicates if bookable

 The actual booking deeplink comes from the Flight Offers Price API,
 but for search results we construct a Google Flights fallback URL or
 use the lastTicketingDateTime to guide the user.

 We try these fields in order:
 1. ``flight_offer["deeplink"]`` — direct booking link (test env may omit)
 2. ``dictionaries["currency"]["metadata"]["bookingUrl"]`` — rare
 3. Fallback: Google Flights search URL constructed from flight data

 Args:
 flight_offer: A single flight offer dict from Amadeus search results.

 Returns:
 A booking URL string, or a Google Flights fallback URL.
 """
 # 1. Direct deeplink (production Amadeus may provide this)
 deeplink = flight_offer.get("deeplink", {}).get("href") or flight_offer.get("deeplink")
 if deeplink and isinstance(deeplink, str) and deeplink.startswith("http"):
 logger.debug("Using Amadeus deeplink for booking URL")
 return deeplink

 # 2. Links section (some Amadeus versions)
 links = flight_offer.get("links", {})
 booking_link = links.get("booking") or links.get("deeplink")
 if booking_link and isinstance(booking_link, str) and booking_link.startswith("http"):
 logger.debug("Using Amadeus links.booking for booking URL")
 return booking_link

 # 3. Fallback: construct Google Flights URL from segments
 try:
 segments = (
 flight_offer.get("itineraries", [{}])[0]
 .get("segments", [])
 )
 if segments:
 first_seg = segments[0]
 last_seg = segments[-1]
 origin = first_seg.get("departure", {}).get("iataCode", "")
 destination = last_seg.get("arrival", {}).get("iataCode", "")
 date = first_seg.get("departure", {}).get("at", "")[:10]
 airline = flight_offer.get("validatingAirlineCodes", [""])[0]

 if origin and destination and date:
 url = (
 f"https://www.google.com/travel/flights"
 f"?q=Flights+from+{origin}+to+{destination}+on+{date}"
 f"&curr=USD"
 )
 if airline:
 url += f"&carrier={airline}"
 logger.debug(f"Using Google Flights fallback URL: {url}")
 return url
 except (IndexError, KeyError, TypeError) as e:
 logger.warning(f"Failed to construct Google Flights fallback URL: {e}")

 # 4. Ultimate fallback
 logger.warning("No booking URL found in Amadeus offer, using generic fallback")
 return "https://www.google.com/travel/flights"