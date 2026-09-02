"""Turns a free-text description of when someone wants to fly ("weekend we
wrześniu", "od 10 do 20 września", "tydzień w listopadzie") into concrete
departure/return date lists, using the same local Ollama model as
travel_intent.py.

Calendar arithmetic is deliberately NOT delegated to the model — small
local models are unreliable at that kind of exact computation (see
travel_intent.py's docstring for the same lesson learned about country and
temperature extraction). The model here only extracts a handful of small,
easily-validated facts (a month, an explicit day-of-month range, a named
trip shape like "weekend"); every actual calendar date is then generated in
plain Python via the standard `calendar` module, which is never wrong about
which day of the week a date falls on.
"""
import calendar
from datetime import date

from core.ollama_client import call_ollama_json

_VALID_TRIP_TYPES = {"weekend", "long_weekend", "week"}

# Python's date.weekday(): Monday=0 ... Sunday=6.
_WEEKEND_DEPARTURE_WEEKDAYS = {3, 4, 5}   # Thu, Fri, Sat
_WEEKEND_RETURN_WEEKDAYS = {5, 6, 0}      # Sat, Sun, Mon
_LONG_WEEKEND_DEPARTURE_WEEKDAYS = {2, 3, 4}  # Wed, Thu, Fri
_LONG_WEEKEND_RETURN_WEEKDAYS = {6, 0, 1}     # Sun, Mon, Tue

# Polish month names decline by grammatical case — "cały wrzesień" (nominative)
# vs. "w wrześniu" (locative) vs. "10 września" (genitive) are all different
# words, not just a suffix change, so each case gets its own lookup rather
# than trying to derive one from another.
_MONTH_NOMINATIVE_PL = {
    1: "styczeń", 2: "luty", 3: "marzec", 4: "kwiecień", 5: "maj", 6: "czerwiec",
    7: "lipiec", 8: "sierpień", 9: "wrzesień", 10: "październik", 11: "listopad", 12: "grudzień",
}
_MONTH_GENITIVE_PL = {
    1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia", 5: "maja", 6: "czerwca",
    7: "lipca", 8: "sierpnia", 9: "września", 10: "października", 11: "listopada", 12: "grudnia",
}
_MONTH_NAMES_PL = {
    1: "styczniu", 2: "lutym", 3: "marcu", 4: "kwietniu", 5: "maju", 6: "czerwcu",
    7: "lipcu", 8: "sierpniu", 9: "wrześniu", 10: "październiku", 11: "listopadzie", 12: "grudniu",
}


def _build_prompt(query: str, today: date) -> str:
    return (
        f'Task: extract structured date preferences from this free-text travel-timing query '
        f'(Polish or English): "{query}". Today\'s date is {today.isoformat()}. '
        "Extract: month as an integer 1-12 if a specific month is named (e.g. 'wrzesień'/'September' "
        "-> 9), else null. day_start/day_end as day-of-month integers ONLY if an explicit day range "
        "is given (e.g. 'od 10 do 20' -> day_start=10, day_end=20), else null. trip_type: "
        "'weekend' if a (short) weekend trip is described, 'long_weekend' if an extended/long "
        "weekend is described, 'week' if a week-long trip is described, else null. Set "
        "understood=false ONLY if the query is empty, gibberish, or expresses no date preference "
        "at all. Respond as JSON only, no other text."
    )


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "month": {"type": ["integer", "null"]},
            "day_start": {"type": ["integer", "null"]},
            "day_end": {"type": ["integer", "null"]},
            "trip_type": {"type": ["string", "null"]},
            "understood": {"type": "boolean"},
        },
        "required": ["month", "day_start", "day_end", "trip_type", "understood"],
    }


def _clean_intent(raw: dict) -> dict:
    """Whitelist/clamp every field — never trust a raw model value directly,
    same principle as travel_intent.py's verification step."""
    month = raw.get("month")
    month = month if isinstance(month, int) and 1 <= month <= 12 else None

    day_start = raw.get("day_start")
    day_start = day_start if isinstance(day_start, int) and 1 <= day_start <= 31 else None

    day_end = raw.get("day_end")
    day_end = day_end if isinstance(day_end, int) and 1 <= day_end <= 31 else None

    trip_type = raw.get("trip_type")
    trip_type = trip_type if trip_type in _VALID_TRIP_TYPES else None

    return {
        "month": month, "day_start": day_start, "day_end": day_end,
        "trip_type": trip_type, "understood": bool(raw.get("understood", True)),
    }


def _resolve_year(month: int, today: date) -> int:
    """A named month that's already behind us this year means next year —
    nobody asking for 'a weekend in March' in November means last March."""
    return today.year + 1 if month < today.month else today.year


def _dates_in_month(year: int, month: int, weekdays=None, day_start=None, day_end=None) -> list[str]:
    days_in_month = calendar.monthrange(year, month)[1]
    start = max(1, day_start or 1)
    end = min(days_in_month, day_end or days_in_month)
    return [
        date(year, month, day).strftime("%Y-%m-%d")
        for day in range(start, end + 1)
        if weekdays is None or date(year, month, day).weekday() in weekdays
    ]


def resolve_dates(query: str, today: date = None):
    """Returns None if `query` is empty or the model doesn't recognize a
    usable date preference in it — callers should fall back to whatever
    exact date fields were entered manually. Otherwise returns a dict:
    {"dates_departure": [...], "dates_back": [...], "min_days": int|None,
    "max_days": int|None, "summary": str} — min/max are None when the query
    doesn't imply a stay-length preference of its own (e.g. a plain day
    range), meaning the caller's own min/max-days setting still applies.

    Raises RuntimeError (Ollama unreachable/misconfigured) the same way
    travel_intent.resolve_destinations does.
    """
    query = (query or "").strip()
    if not query:
        return None

    today = today or date.today()
    intent = _clean_intent(call_ollama_json(_build_prompt(query, today), _schema()))

    if not intent["understood"] or intent["month"] is None:
        # No recognized month means nothing concrete to build dates from —
        # better to fall back to the manual fields than guess a month.
        return None

    month = intent["month"]
    year = _resolve_year(month, today)
    month_label = f"{_MONTH_NAMES_PL[month]} {year}"

    if intent["day_start"] or intent["day_end"]:
        dates = _dates_in_month(year, month, day_start=intent["day_start"], day_end=intent["day_end"])
        start_label = intent["day_start"] or 1
        end_label = intent["day_end"] or calendar.monthrange(year, month)[1]
        return {
            "dates_departure": dates, "dates_back": dates, "min_days": None, "max_days": None,
            "summary": f"✅ Zrozumiano: {start_label}–{end_label} {_MONTH_GENITIVE_PL[month]} {year}",
        }

    if intent["trip_type"] == "weekend":
        return {
            "dates_departure": _dates_in_month(year, month, weekdays=_WEEKEND_DEPARTURE_WEEKDAYS),
            "dates_back": _dates_in_month(year, month, weekdays=_WEEKEND_RETURN_WEEKDAYS),
            "min_days": 1, "max_days": 3,
            "summary": f"✅ Zrozumiano: weekendy w {month_label} (wylot czw–sob, powrót sob–pon)",
        }

    if intent["trip_type"] == "long_weekend":
        return {
            "dates_departure": _dates_in_month(year, month, weekdays=_LONG_WEEKEND_DEPARTURE_WEEKDAYS),
            "dates_back": _dates_in_month(year, month, weekdays=_LONG_WEEKEND_RETURN_WEEKDAYS),
            "min_days": 3, "max_days": 5,
            "summary": f"✅ Zrozumiano: długie weekendy w {month_label} (wylot śr–pt, powrót nd–wt)",
        }

    if intent["trip_type"] == "week":
        dates = _dates_in_month(year, month)
        return {
            "dates_departure": dates, "dates_back": dates, "min_days": 6, "max_days": 8,
            "summary": f"✅ Zrozumiano: tygodniowy wyjazd w {month_label}",
        }

    # A month was named but no day range or trip shape — scan the whole
    # month, leave the stay-length preference (min/max days) untouched.
    dates = _dates_in_month(year, month)
    return {
        "dates_departure": dates, "dates_back": dates, "min_days": None, "max_days": None,
        "summary": f"✅ Zrozumiano: cały {_MONTH_NOMINATIVE_PL[month]} {year}",
    }
