from core.search import build_legs, te_same_regiony, znajdz_polaczenia_dwustronne
from core.utils import generate_dates


def flight(origin, destination, date, price):
    return {"origin": origin, "destination": destination, "date": date, "price": price}


def test_generate_dates_is_inclusive():
    assert generate_dates("2026-09-29", "2026-10-02") == [
        "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02",
    ]


def test_generate_dates_single_day():
    assert generate_dates("2026-09-01", "2026-09-01") == ["2026-09-01"]


def test_build_legs_covers_both_directions():
    legs = build_legs({
        "origins": ["KRK"],
        "destinations": ["BCN", "PMI"],
        "dates_departure": ["2026-09-01"],
        "dates_back": ["2026-09-05"],
    })
    assert legs == [
        ("KRK", "BCN", "2026-09-01"),
        ("KRK", "PMI", "2026-09-01"),
        ("BCN", "KRK", "2026-09-05"),
        ("PMI", "KRK", "2026-09-05"),
    ]


def test_te_same_regiony():
    groups = [["BCN", "GRO"], ["KRK", "KTW"]]
    assert te_same_regiony("BCN", "GRO", groups)
    assert not te_same_regiony("BCN", "KRK", groups)
    assert not te_same_regiony("BCN", "GRO", [])


def test_pairs_round_trip_within_stay_range_sorted_by_price():
    flights = [
        flight("KRK", "BCN", "2026-09-01", 200.0),
        flight("BCN", "KRK", "2026-09-04", 150.0),
        flight("BCN", "KRK", "2026-09-03", 300.0),
        flight("BCN", "KRK", "2026-09-20", 10.0),  # stay too long
    ]
    offers = znajdz_polaczenia_dwustronne(flights, [], [], min_days=2, max_days=5)

    assert [(o["cena"], o["pobyt"]) for o in offers] == [(350.0, 3), (500.0, 2)]


def test_pairs_across_grouped_airports():
    flights = [
        flight("KRK", "BCN", "2026-09-01", 100.0),
        flight("GRO", "KTW", "2026-09-04", 80.0),
    ]
    assert znajdz_polaczenia_dwustronne(flights, [], [], 1, 7) == []

    offers = znajdz_polaczenia_dwustronne(flights, [["BCN", "GRO"]], [["KRK", "KTW"]], 1, 7)
    assert len(offers) == 1
    assert offers[0]["cena"] == 180.0


def test_skips_legs_with_malformed_dates():
    flights = [
        flight("KRK", "BCN", "not-a-date", 100.0),
        flight("BCN", "KRK", "2026-09-04", 80.0),
    ]
    assert znajdz_polaczenia_dwustronne(flights, [], [], 0, 30) == []
