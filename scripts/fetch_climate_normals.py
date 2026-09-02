"""One-time (re-runnable) build script: precompute average daytime
temperature per month for every curated airport, from Open-Meteo's free
historical archive API (no key required), and write the result to
app/static/climate_normals.json.

This is NOT called at request time — the app only ever reads the static
JSON this script produces (see app/core/weather.py), so a live search never
depends on Open-Meteo being up. Re-run this occasionally (e.g. yearly) to
keep the normals current; it's cheap (one HTTP call per airport) and safe
to re-run — it always overwrites the whole file from scratch.

Usage:
    venv/bin/python scripts/fetch_climate_normals.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
START_DATE = "2020-01-01"
END_DATE = "2025-12-31"  # six full years of history to average over
REQUEST_DELAY_SECONDS = 0.3  # be polite to a free, unauthenticated API

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AIRPORTS_PATH = os.path.join(BASE_DIR, "app", "static", "airports.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "app", "static", "climate_normals.json")


def fetch_monthly_avg_max(lat, lon):
    """Return {month (1-12): average daily-high temp in °C} for this
    location, averaged over START_DATE..END_DATE, or None on failure."""
    url = (
        f"{ARCHIVE_URL}?latitude={lat}&longitude={lon}"
        f"&start_date={START_DATE}&end_date={END_DATE}"
        f"&daily=temperature_2m_max&timezone=auto"
    )
    data = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.load(resp)
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"  ⚠️ zapytanie nieudane (próba {attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(2)
    if data is None:
        return None

    dates = data.get("daily", {}).get("time", [])
    temps = data.get("daily", {}).get("temperature_2m_max", [])
    if not dates or len(dates) != len(temps):
        print("  ⚠️ nieoczekiwana odpowiedź API")
        return None

    sums = {m: 0.0 for m in range(1, 13)}
    counts = {m: 0 for m in range(1, 13)}
    for date_str, temp in zip(dates, temps):
        if temp is None:
            continue
        month = int(date_str.split("-")[1])
        sums[month] += temp
        counts[month] += 1

    return {
        str(m): round(sums[m] / counts[m], 1)
        for m in range(1, 13)
        if counts[m] > 0
    }


def main():
    with open(AIRPORTS_PATH, encoding="utf-8") as f:
        airports = json.load(f)

    normals = {}
    for i, airport in enumerate(airports, 1):
        code = airport["code"]
        print(f"[{i}/{len(airports)}] {code} ({airport['city']})...")
        monthly = fetch_monthly_avg_max(airport["lat"], airport["lon"])
        if monthly:
            normals[code] = monthly
        else:
            print(f"  ❌ pomijam {code} — brak danych klimatycznych")
        time.sleep(REQUEST_DELAY_SECONDS)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(normals, f, ensure_ascii=False, indent=1, sort_keys=True)

    print(f"\n✅ Zapisano normy klimatyczne dla {len(normals)}/{len(airports)} lotnisk -> {OUTPUT_PATH}")
    if len(normals) < len(airports):
        print("⚠️ Część lotnisk nie ma danych — uruchom ponownie, jeśli to był tymczasowy błąd sieci.")
        sys.exit(1)


if __name__ == "__main__":
    main()
