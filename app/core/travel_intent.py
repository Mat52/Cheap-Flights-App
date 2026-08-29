"""Turns a free-text description of where someone wants to fly ("Hiszpania",
"gdziekolwiek gdzie jest ponad 20 stopni") into a concrete list of
destination airport codes, using a local Ollama model — no cloud API, no
key, no cost.

A small local model is fast but, measured directly against this app's own
test queries, unreliable on its own: llama3.1:8b invented a country that
was never mentioned for an unsupported-place query ("Japonia" -> "Italy"),
and separately parroted the example numbers from this file's own prompt
("mild=15") into queries that never mentioned a temperature at all. Neither
failure is something a JSON-schema/enum constraint prevents — the schema
only constrains which *values* are legal, not whether the model should have
said anything at all. So every country and every temperature the model
returns is re-verified in plain Python against the actual query text before
being trusted (see _verify_against_query) — this is not optional polish,
it's what makes the local-model answer safe to act on.
"""
import re
import unicodedata

from core import weather
from core.ollama_client import call_ollama_json

# Keywords that indicate the query expresses *some* weather/temperature
# preference at all — if none of these appear, any min_avg_temp_c the model
# returns is discarded rather than trusted (see the docstring above: small
# models have been observed parroting this file's own example numbers into
# queries that never mentioned temperature).
_TEMPERATURE_KEYWORDS = [
    "stopni", "stopnie", "stopien", "cieplej", "cieplo", "goraco", "zimno",
    "chlodno", "temperatur", "degree", "warm", "hot", "cold", "mild", "celsius",
]

_POLISH_DIACRITICS = str.maketrans("ąćęłńóśźż", "acelnoszz")


def _normalize(text: str) -> str:
    """Lowercase and strip Polish diacritics so 'Włochy' matches a query
    typed as 'wlochy', and generally so comparisons aren't diacritic-sensitive."""
    text = unicodedata.normalize("NFKD", text.lower())
    return text.translate(_POLISH_DIACRITICS)


def _mentions_temperature(query: str) -> bool:
    normalized = _normalize(query)
    return any(kw in normalized for kw in _TEMPERATURE_KEYWORDS) or bool(re.search(r"\d+\s*°", query))


def _restore_diacritics(query: str, translations: dict) -> str:
    """Best-effort: rewrite an ASCII-typed Polish country name ('Wlochy')
    back to its accented form ('Włochy') before the model sees it.

    Verified this matters: asking for "Wlochy albo Grecja" made the model
    miss Italy entirely, while "Włochy albo Grecja" (and "Italy or Greece")
    both matched correctly every time — a small local model recognizes the
    accented form far more reliably than an unaccented one. _normalize()
    already strips diacritics both ways for the later verification step, so
    this only needs to help the model's own generation, not the check.
    """
    lowered = query.lower()
    normalized = _normalize(query)
    for name in set(translations.values()):
        accented = name.lower()
        stripped = _normalize(name)
        if stripped == accented:
            continue  # nothing to restore
        for m in re.finditer(r"\b" + re.escape(stripped) + r"\b", normalized):
            start, end = m.span()
            lowered = lowered[:start] + accented + lowered[end:]
    return lowered


def _build_prompt(query: str, countries: list[str]) -> str:
    country_list = ", ".join(countries)
    return (
        f'Task: extract structured travel-destination criteria from this free-text query '
        f'(Polish or English): "{query}". '
        f"Rules: countries must come ONLY from this exact list, never invent one: {country_list}. "
        "If the query does NOT name any specific country or region, return an EMPTY countries "
        "array — do not list every country. Expand broad phrases (e.g. 'southern Europe') into "
        "matching countries from that list. If a temperature preference is expressed without an "
        "exact number, use a reasonable Celsius threshold (warm=20, hot=27, mild=15) — but if NO "
        "temperature or weather preference is expressed at all, min_avg_temp_c must be null. "
        "Set understood=false ONLY if the query is empty, gibberish, or expresses no "
        "travel-destination preference at all. Set requested_unsupported_place=true ONLY if the "
        "query names a real country/region NOT in the allowed list (e.g. Japan, USA). "
        "Respond as JSON only, no other text."
    )


def _schema(countries: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "countries": {"type": "array", "items": {"type": "string", "enum": countries}},
            "min_avg_temp_c": {"type": ["number", "null"]},
            "understood": {"type": "boolean"},
            "requested_unsupported_place": {"type": "boolean"},
        },
        "required": ["countries", "min_avg_temp_c", "understood", "requested_unsupported_place"],
    }


def _verify_against_query(result: dict, query: str) -> dict:
    """Re-check the model's answer against the actual query text — see the
    module docstring for why this isn't optional. Every country has to be
    named (directly, or by its Polish translation) somewhere in the query;
    a temperature is only kept if the query expresses a weather preference
    at all. Anything dropped this way that the model *did* claim flips
    requested_unsupported_place on, so the caller reports "no match" rather
    than silently treating a rejected guess as "no preference" (= everywhere).
    """
    normalized_query = _normalize(query)
    countries = result.get("countries") or []
    translations = result.get("_translations", {})

    verified = [
        c for c in countries
        if _normalize(c) in normalized_query or _normalize(translations.get(c, "")) in normalized_query
    ]
    dropped_any = len(verified) < len(countries)

    temp = result.get("min_avg_temp_c")
    if temp is not None and not _mentions_temperature(query):
        temp = None
        dropped_any = True

    return {
        "countries": verified,
        "min_avg_temp_c": temp,
        "understood": bool(result.get("understood", True)),
        "requested_unsupported_place": bool(result.get("requested_unsupported_place", False)) or (
            dropped_any and not verified and temp is None
        ),
    }


def parse_travel_query(query: str, countries: list[str], translations: dict) -> dict:
    """Returns {"countries": [...], "min_avg_temp_c": float|None, "understood": bool,
    "requested_unsupported_place": bool} — already verified against the query text.

    Raises RuntimeError with a Polish, user-facing message if Ollama itself
    is unreachable/misconfigured.
    """
    raw = call_ollama_json(_build_prompt(_restore_diacritics(query, translations), countries), _schema(countries))
    raw["_translations"] = translations
    return _verify_against_query(raw, query)


def resolve_destinations(query: str, airports: list[dict], travel_month: int):
    """Turn a free-text query into (destination_airport_codes, intent).

    An empty query means "anywhere" (every curated airport) — no model call
    made. A non-empty query the model doesn't recognize as any kind of
    travel preference also falls back to "anywhere". A recognized
    preference that matches zero airports (e.g. a country outside this
    app's network, or an unreachable temperature) returns an empty list on
    purpose — the caller should show "no matches", not silently search
    everywhere.
    """
    query = (query or "").strip()
    if not query:
        return [a["code"] for a in airports], {
            "countries": [], "min_avg_temp_c": None, "understood": False, "requested_unsupported_place": False,
        }

    countries = sorted({a["country"] for a in airports})
    translations = {a["country"]: a["region"] for a in airports}
    intent = parse_travel_query(query, countries, translations)

    if not intent["understood"]:
        return [a["code"] for a in airports], intent

    if intent["requested_unsupported_place"] and not intent["countries"] and intent["min_avg_temp_c"] is None:
        # A real place was named, just not one this app's network covers —
        # report "no matches", don't silently widen to "everywhere".
        return [], intent

    candidates = airports
    if intent["countries"]:
        wanted = set(intent["countries"])
        candidates = [a for a in candidates if a["country"] in wanted]

    if intent["min_avg_temp_c"] is not None:
        threshold = intent["min_avg_temp_c"]
        filtered = []
        for a in candidates:
            temp = weather.avg_temp_c(a["code"], travel_month)
            if temp is not None and temp >= threshold:
                filtered.append(a)
        candidates = filtered

    return [a["code"] for a in candidates], intent
