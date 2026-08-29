"""Core search logic, shared by the web UI: scan a set of routes/dates for
one-way legs, then pair them into round-trip offers.

This is the same matching logic the old main.py used, extracted so it isn't
tied to a hardcoded config module — callers pass everything as `params`.
"""
from datetime import datetime

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


def run_search(page, params, on_result=None):
    """Scan every origin x destination x date combo in both directions.

    `params` needs: origins, destinations, dates_departure, dates_back,
    grupy_baz, grupy_destynacji, min_days, max_days.
    `on_result(flight_dict)`, if given, is called for each leg found as
    soon as it's found (e.g. to persist it incrementally).

    Returns (all_legs_found, round_trip_offers_sorted_by_price).
    """
    results = []
    cookies = True

    for origin in params["origins"]:
        for destination in params["destinations"]:
            for date in params["dates_departure"]:
                result = search_flight_google(page, origin, destination, date, cookies)
                cookies = False
                if result:
                    results.append(result)
                    if on_result:
                        on_result(result)

    for destination in params["destinations"]:
        for origin in params["origins"]:
            for date in params["dates_back"]:
                result = search_flight_google(page, destination, origin, date, cookies)
                if result:
                    results.append(result)
                    if on_result:
                        on_result(result)

    offers = znajdz_polaczenia_dwustronne(
        results,
        params["grupy_destynacji"],
        params["grupy_baz"],
        params["min_days"],
        params["max_days"],
    )
    return results, offers
