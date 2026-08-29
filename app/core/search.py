"""Core search logic, shared by the web UI: scan a set of routes/dates for
one-way legs, then pair them into round-trip offers.

Legs are scraped concurrently (bounded by `concurrency`), and any leg
already scraped within `cache_max_age_minutes` is read straight from
Postgres instead of hitting Google Flights again — so re-running an
overlapping search a few minutes later reuses what's already known instead
of re-scraping everything, and a fully-cached search never launches a
browser at all.
"""
import asyncio
from datetime import datetime

import database
from core.googleflights import search_flight_google


def te_same_regiony(a, b, grupy):
    """Sprawdza, czy dwa kody lotnisk należą do tej samej grupy."""
    return any(a in grupa and b in grupa for grupa in grupy)


def znajdz_polaczenia_dwustronne(loty, grupy_destynacji, grupy_baz, min_days, max_days):
    polaczenia = []
    for wylot in loty:
        for powrot in loty:
            if (
                wylot['origin'] != wylot['destination']
                and (wylot['destination'] == powrot['origin'] or te_same_regiony(wylot['destination'], powrot['origin'], grupy_destynacji))
                and (wylot['origin'] == powrot['destination'] or te_same_regiony(wylot['origin'], powrot['destination'], grupy_baz))
                and wylot != powrot
            ):
                try:
                    data_wylotu = datetime.strptime(wylot['date'], "%Y-%m-%d")
                    data_powrotu = datetime.strptime(powrot['date'], "%Y-%m-%d")
                except ValueError:
                    continue
                roznica = (data_powrotu - data_wylotu).days
                if min_days <= roznica <= max_days:
                    polaczenia.append({
                        "tam": wylot,
                        "powrot": powrot,
                        "cena": round(wylot['price'] + powrot['price'], 2),
                        "pobyt": roznica,
                    })
    return sorted(polaczenia, key=lambda x: x["cena"])


def build_legs(params):
    """Flatten origins x destinations x dates (both directions) into one
    flat list of (origin, destination, date) one-way legs to look up."""
    legs = []
    for origin in params["origins"]:
        for destination in params["destinations"]:
            for date in params["dates_departure"]:
                legs.append((origin, destination, date))
    for destination in params["destinations"]:
        for origin in params["origins"]:
            for date in params["dates_back"]:
                legs.append((destination, origin, date))
    return legs


async def split_cached(legs, cache_max_age_minutes):
    """Split `legs` into (already-fresh-in-db, still-need-to-scrape).

    Cache lookups are plain indexed SELECTs (see database.get_recent_flight)
    run off the event loop thread via asyncio.to_thread, so a slow/unreachable
    DB just falls back to "no cache hit" per leg rather than blocking or
    failing the whole search.
    """
    if not cache_max_age_minutes:
        return [], list(legs)

    hits = await asyncio.gather(
        *(asyncio.to_thread(database.get_recent_flight, origin, destination, date, cache_max_age_minutes)
          for origin, destination, date in legs)
    )

    cached_results, to_scrape = [], []
    for (origin, destination, date), hit in zip(legs, hits):
        if hit:
            cached_results.append(hit)
        else:
            to_scrape.append((origin, destination, date))
    return cached_results, to_scrape


async def scrape_legs(context, legs, concurrency):
    """Scrape every (origin, destination, date) leg concurrently, at most
    `concurrency` Playwright pages open at once, all sharing `context` (one
    browser, many pages — cheaper than one context per leg)."""
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def scrape_one(origin, destination, date):
        async with semaphore:
            page = await context.new_page()
            try:
                return await search_flight_google(page, origin, destination, date)
            finally:
                await page.close()

    return await asyncio.gather(*(scrape_one(origin, destination, date) for origin, destination, date in legs))


async def run_search(launch_browser, params, on_result=None, concurrency=5, cache_max_age_minutes=30):
    """Scan every origin x destination x date combo in both directions.

    `launch_browser` is an async, zero-arg callable returning a freshly
    launched Playwright Browser — it's only called (and the browser only
    closed) if there's at least one leg not already covered by the cache,
    so a search that's entirely cache hits never starts a browser at all.
    `on_result(flight_dict)`, if given, is called for each *freshly scraped*
    leg as soon as it's found (e.g. to persist it) — cache hits are already
    in the database, so they're not re-persisted.

    Returns (all_legs_found, round_trip_offers_sorted_by_price).
    """
    legs = build_legs(params)
    cached_results, to_scrape = await split_cached(legs, cache_max_age_minutes)
    results = list(cached_results)

    if cached_results:
        print(f"💾 {len(cached_results)}/{len(legs)} odcinków wziętych z cache (bez scrapowania)")

    if to_scrape:
        browser = await launch_browser()
        try:
            context = await browser.new_context()
            # Bounds every Playwright wait that doesn't specify its own
            # timeout, for every page created from this context.
            context.set_default_timeout(8000)
            scraped = await scrape_legs(context, to_scrape, concurrency)
            for flight in scraped:
                if flight:
                    results.append(flight)
                    if on_result:
                        await asyncio.to_thread(on_result, flight)
        finally:
            await browser.close()

    offers = znajdz_polaczenia_dwustronne(
        results,
        params["grupy_destynacji"],
        params["grupy_baz"],
        params["min_days"],
        params["max_days"],
    )
    return results, offers
