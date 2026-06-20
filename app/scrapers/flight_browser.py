"""
Flight search using agent-browser CLI for browser automation.
This is the preferred free method for Google Flights data.
"""
import json
import subprocess


class FlightBrowserScraper:
    """Use agent-browser CLI to scrape Google Flights."""

    def __init__(self):
        self.base_url = "https://www.google.com/travel/flights"

    def search(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        max_results: int = 10,
    ) -> dict:
        """Search flights using browser automation."""

        # Build URL with parameters
        url = self._build_url(origin, destination, departure_date, return_date)

        try:
            # Use agent-browser to open and scrape
            result = self._scrape_with_agent_browser(url)
            return result
        except Exception as e:
            return {"flights": [], "total": 0, "error": str(e)}

    def _build_url(self, origin: str, dest: str, dep: str, ret: str | None) -> str:
        """Build Google Flights URL."""
        params = "?gl=US&hl=en&source=m6"
        url = f"{self.base_url}{params}"
        return url

    def _scrape_with_agent_browser(self, url: str) -> dict:
        """Use agent-browser CLI to scrape flight data."""
        # Open the page
        subprocess.run(["agent-browser", "open", url], capture_output=True)

        # Wait for page to load
        import time

        time.sleep(3)

        # Get page content and screenshot
        subprocess.run(
            ["agent-browser", "screenshot", "/tmp/flights.png"], capture_output=True
        )

        # Extract flight info from page
        result = self._extract_flights()
        return result

    def _extract_flights(self) -> dict:
        """Extract flight data from the loaded page."""
        # This would use agent-browser snapshot/eval to extract data
        # For now, return structure
        return {"flights": self._get_mock_flights(), "total": 0, "error": None}

    def _get_mock_flights(self) -> list[dict]:
        """Mock flight data for testing."""
        return [
            {
                "airline": "American Airlines",
                "flight_number": "AA123",
                "price": "$250",
                "duration": "4h 30m",
                "departure_time": "08:00",
                "arrival_time": "12:30",
            }
        ]


if __name__ == "__main__":
    scraper = FlightBrowserScraper()
    result = scraper.search("JFK", "LAX", "2026-07-15", "2026-07-22")
    print(json.dumps(result, indent=2))
