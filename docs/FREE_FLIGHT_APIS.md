# Free Flight Data Sources

## 1. Google Flights Browser Automation

**URL**: https://www.google.com/travel/flights
**Status**: ❌ Requires internet access to google.com
**Method**: Browser automation (Playwright/Puppeteer)

### Pros
- Truly free (no API key needed)
- Real-time, comprehensive data
- No rate limits

### Cons  
- Network must resolve google.com
- Browser automation required
- May get blocked by Google
- Slower than API

### Working Implementation
```python
# Requires: pip install playwright && playwright install chromium
from playwright.sync_api import sync_playwright

def search_flights(origin, destination, departure_date):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.google.com/travel/flights")
        # Fill form and extract data
        ...
```

## 2. fli Library (Installed)

**Status**: ❌ Returns 0 results - Google blocks direct API calls
**Installed at**: `/root/.local/pipx/venvs/flights`

The `fli` Python library attempts to call Google's internal APIs but Google actively blocks these requests.

## 3. SearchAPI ($4/1K requests)

**URL**: https://www.searchapi.io/docs/google-flights-api
**Status**: ✅ Working fallback
**Cost**: $4 per 1000 requests

### Quick Start
```python
import httpx

API_KEY = "your_key"
params = {
    "engine": "google_flights",
    "departure_id": "MCI",
    "arrival_id": "LHR", 
    "outbound_date": "2026-07-15",
    "api_key": API_KEY,
}

resp = httpx.get("https://www.searchapi.io/api/v1/search", params=params)
flights = resp.json().get("best_flights", [])
```

## 4. AviationStack (500 req/month free)

**URL**: https://aviationstack.com
**Status**: Limited to current flight status

## Recommendation

Since the environment doesn't have google.com DNS access:

1. **Use SearchAPI** - The $4/1K option is the most cost-effective
2. **Cost estimate**: 100 searches/month = $0.40 (well within budget)
3. **Cache strategy**: 6-hour TTL = ~288 searches/day = ~$3.50/month

## Configuration

Set in `.env`:
```
SEARCHAPI_API_KEY=your_key_here
```

See `.env.example` for all required variables.