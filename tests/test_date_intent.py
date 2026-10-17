from datetime import date

import pytest

from core import date_intent

TODAY = date(2026, 8, 15)


@pytest.fixture
def model_returns(monkeypatch):
    """Stub the Ollama call so tests exercise only the Python calendar logic."""
    def _set(response):
        monkeypatch.setattr(date_intent, "call_ollama_json", lambda prompt, schema: response)
    return _set


def test_empty_query_skips_the_model():
    assert date_intent.resolve_dates("   ", today=TODAY) is None


def test_weekend_dates_fall_on_the_right_weekdays(model_returns):
    model_returns({"month": 9, "trip_type": "weekend", "understood": True})
    result = date_intent.resolve_dates("weekend we wrześniu", today=TODAY)

    departures = [date.fromisoformat(d).weekday() for d in result["dates_departure"]]
    returns = [date.fromisoformat(d).weekday() for d in result["dates_back"]]
    assert set(departures) == {3, 4, 5}  # Thu, Fri, Sat
    assert set(returns) == {5, 6, 0}     # Sat, Sun, Mon
    assert (result["min_days"], result["max_days"]) == (1, 3)


def test_explicit_day_range(model_returns):
    model_returns({"month": 9, "day_start": 10, "day_end": 12, "understood": True})
    result = date_intent.resolve_dates("od 10 do 12 września", today=TODAY)

    assert result["dates_departure"] == ["2026-09-10", "2026-09-11", "2026-09-12"]
    assert result["min_days"] is None


def test_past_month_rolls_over_to_next_year(model_returns):
    model_returns({"month": 3, "trip_type": "week", "understood": True})
    result = date_intent.resolve_dates("tydzień w marcu", today=TODAY)

    assert result["dates_departure"][0] == "2027-03-01"
    assert len(result["dates_departure"]) == 31


def test_out_of_range_model_values_are_rejected(model_returns):
    model_returns({"month": 13, "trip_type": "weekend", "understood": True})
    assert date_intent.resolve_dates("weekend", today=TODAY) is None


def test_day_range_is_clamped_to_month_length(model_returns):
    model_returns({"month": 9, "day_start": 29, "day_end": 31, "understood": True})
    result = date_intent.resolve_dates("koniec września", today=TODAY)

    assert result["dates_departure"] == ["2026-09-29", "2026-09-30"]
