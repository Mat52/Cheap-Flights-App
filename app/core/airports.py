"""Server-side access to the same curated airport list the page's picker UI
loads client-side from /static/airports.json (code, name, city, country,
region, lat, lon) — needed here so travel_intent can resolve a free-text
query against the real list of covered airports/countries.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "airports.json")
_cache = None


def load_airports():
    global _cache
    if _cache is None:
        with open(_PATH, encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache
