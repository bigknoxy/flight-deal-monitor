"""
Flight search using agent-browser CLI for browser automation.
"""
import subprocess
import json
import time
from typing import Optional, List, Dict

def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    max_results: int = 10,
) -> Dict:
    """Search Google Flights using agent-browser CLI."""
    
    # Build URL
    url = f"https://www.google.com/travel/flights?gl=US&hl=en&curr=USD"
    
    # Open page
    subprocess.run(["agent-browser", "open", url], capture_output=True)
    time.sleep(2)
    
    # Fill form using agent-browser eval
    fill_script = f'''
    // Fill origin
    const originInput = document.querySelector('[aria-label="Where from?"]');
    if (originInput) {{
        originInput.click();
        originInput.value = "{origin}";
        originInput.dispatchEvent(new Event('input', {{bubbles: true}}));
    }}
    
    // Fill destination
    const destInput = document.querySelector('[aria-label="Where to?"]');
    if (destInput) {{
        destInput.click();
        destInput.value = "{destination}";
        destInput.dispatchEvent(new Event('input', {{bubbles: true}}));
    }}
    
    // Fill dates
    const depInput = document.querySelector('input[label="Departure"], input[aria-label*="Departure"]');
    if (depInput) {{
        depInput.value = "{departure_date}";
    }}
    
    // Submit
    setTimeout(() => {{
        document.querySelector('button[type="submit"]')?.click();
    }}, 500);
    '''
    
    subprocess.run(["agent-browser", "eval", fill_script], capture_output=True)
    time.sleep(3)
    
    # Extract data
    extract_script = '''
    const flights = [];
    const cards = document.querySelectorAll('[data-test-id="flight-card"], .yycvvf');
    
    for (const card of cards) {
        const airline = card.querySelector('.aIHm1e, [data-test-id="airline-name"]')?.textContent || '';
        const price = card.querySelector('.LlfXrf, [data-test-id="price"]')?.textContent || '';
        const duration = card.querySelector('.liXPdc, [data-test-id="duration"]')?.textContent || '';
        const times = card.querySelectorAll('.wHS9iO, [data-test-id="time"]');
        
        flights.push({
            airline: airline.trim(),
            price: price.trim(),
            duration: duration.trim(),
            departure_time: times[0]?.textContent?.trim() || '',
            arrival_time: times[1]?.textContent?.trim() || ''
        });
    }
    
    flights.slice(0, 10);
    '''
    
    result = subprocess.run(
        ["agent-browser", "eval", extract_script],
        capture_output=True,
        text=True
    )
    
    return {
        "flights": json.loads(result.stdout) if result.stdout else [],
        "total": 0,
        "error": None
    }
