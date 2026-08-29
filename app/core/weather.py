"""Lookup into the precomputed climate normals (see
scripts/fetch_climate_normals.py) — average daily-high temperature per
airport per calendar month, sourced once from Open-Meteo's free historical
archive API. Nothing here makes a network call: this only reads the static
JSON the script produces, so a live search never depends on a weather API
being reachable.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "climate_normals.json")
_cache = None


def _load():
    global _cache
    if _cache is None:
        try:
            with open(_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Brak {_PATH} — uruchom scripts/fetch_climate_normals.py. Filtrowanie po temperaturze nic nie znajdzie.")
            _cache = {}
    return _cache


def avg_temp_c(airport_code, month):
    """Average historical daily-high temperature (°C) for this airport in
    the given calendar month (1-12), or None if unknown (missing airport or
    the climate-normals file hasn't been generated yet)."""
    return _load().get(airport_code, {}).get(str(month))
