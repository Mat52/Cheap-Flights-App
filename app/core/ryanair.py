"""Ryanair's own fare-finder API — used instead of scraping Google Flights
for watchlist entries pinned to Ryanair specifically. This is the same
internal API Ryanair's own website calls to draw its fare calendar, not a
published/supported public API: no key is needed, but its shape or
availability could change without notice, same risk class as any scraper.

Confirmed live against Google Flights: for KRK->RHO on 2026-09-17, this
returned 217.33 PLN on the 19:05-22:45 flight, matching (to the zloty)
what Google Flights showed for the same flight scraped moments later —
see search_flight_google_for_airline()'s docstring in googleflights.py for
the volatility problem this sidesteps. Worth using over the scraper
whenever the entry is pinned to Ryanair and direct_only (the default),
since it's a single JSON GET with no browser, no DOM selectors to break,
and no Google-side result caching/volatility in the middle.

Doesn't cover connections (Ryanair Connect itineraries) — this endpoint is
a direct origin/destination lookup and only ever returns Ryanair's own
point-to-point fare, so callers should fall back to the scraper when an
entry explicitly sets "direct_only": false.
"""
import requests

FARFND_URL = "https://services-api.ryanair.com/farfnd/v4/oneWayFares/{origin}/{destination}/cheapestPerDay"


def get_ryanair_price(origin, destination, date):
    """Look up Ryanair's own fare for one exact date on one route. Returns
    the same shape as search_flight_google()'s result dict, or None if the
    route/date isn't found, isn't on sale, or the request itself fails.
    """
    month_start = date[:8] + "01"  # the API takes a whole month; we filter to one day below
    url = FARFND_URL.format(origin=origin, destination=destination)
    try:
        resp = requests.get(
            url,
            params={"outboundMonthOfDate": month_start, "currency": "PLN"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
        fares = resp.json()["outbound"]["fares"]
    except Exception as e:
        print(f"❌ Błąd Ryanair API ({origin} -> {destination}, {date}): {e}")
        return None

    fare = next((f for f in fares if f["day"] == date), None)
    if not fare or fare.get("unavailable") or not fare.get("price"):
        print(f"ℹ️ Ryanair API: brak lotu {origin} -> {destination} w dniu {date}")
        return None

    departure_date, arrival_date = fare.get("departureDate"), fare.get("arrivalDate")
    departure = departure_date[11:16] if departure_date else "brak danych"
    arrival = arrival_date[11:16] if arrival_date else "brak danych"

    return {
        "origin": origin,
        "destination": destination,
        "date": date,
        "price": round(fare["price"]["value"], 2),
        "Airline": "Ryanair",
        "departure": departure,
        "arrival": arrival,
    }
