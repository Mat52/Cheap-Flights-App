"""Turns a free-text description of where someone wants to fly ("Hiszpania",
"gdziekolwiek gdzie jest ponad 20 stopni") into a concrete list of
destination airport codes — Claude interprets the text against the real
list of countries this app covers, and any temperature preference is then
applied in plain Python against the precomputed climate normals (see
core.weather), never left to the model to "know" real weather data.
"""
import anthropic

from core import weather

MODEL = "claude-opus-5"

_TOOL_NAME = "extract_travel_intent"


def _build_tool(countries):
    return {
        "name": _TOOL_NAME,
        "description": (
            "Extract structured destination criteria from a free-text description "
            "of where someone wants to fly on holiday. Expand broad geographic "
            "phrases ('southern Europe', 'the Mediterranean', 'Scandinavia', "
            "'gdziekolwiek ciepło') into every matching country from the allowed "
            "list — never invent a country outside it. If a temperature "
            "preference is expressed without an exact number, use a reasonable "
            "threshold in Celsius (warm/ciepło≈20, hot/gorąco≈27, very hot≈30, "
            "mild≈15)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "countries": {
                    "type": "array",
                    "items": {"type": "string", "enum": countries},
                    "description": "Every allowed-list country matching the query. Empty if no country/region preference is expressed, or if the requested place isn't on the list.",
                },
                "min_avg_temp_c": {
                    "type": ["number", "null"],
                    "description": "Minimum desired average daytime temperature in Celsius for the travel month, or null if no weather preference is expressed.",
                },
                "understood": {
                    "type": "boolean",
                    "description": "False only if the query is empty, gibberish, or expresses no usable travel-destination preference at all.",
                },
                "requested_unsupported_place": {
                    "type": "boolean",
                    "description": "True only if the query names a specific country/region that is NOT in the allowed list (e.g. USA, Japan, Thailand) — as opposed to expressing no location preference at all (e.g. 'somewhere cheap', 'anywhere').",
                },
            },
            "required": ["countries", "min_avg_temp_c", "understood", "requested_unsupported_place"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def parse_travel_query(query: str, countries: list[str]) -> dict:
    """Returns {"countries": [...], "min_avg_temp_c": float|None, "understood": bool,
    "requested_unsupported_place": bool}.

    Raises RuntimeError with a Polish, user-facing message if the Claude call
    itself fails (bad/missing API key, network, rate limit, ...) — callers
    should catch this and surface it rather than guessing a destination.
    """
    client = anthropic.Anthropic()
    tool = _build_tool(countries)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            output_config={"effort": "low"},
            tools=[tool],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": query}],
        )
    except anthropic.AuthenticationError as e:
        raise RuntimeError("Klucz ANTHROPIC_API_KEY jest nieprawidłowy lub nieskonfigurowany.") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError("Limit zapytań do Claude API został przekroczony, spróbuj ponownie za chwilę.") from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Nie udało się zinterpretować zapytania (błąd Claude API): {e}") from e

    for block in response.content:
        if block.type == "tool_use" and block.name == _TOOL_NAME:
            result = block.input
            return {
                "countries": result.get("countries") or [],
                "min_avg_temp_c": result.get("min_avg_temp_c"),
                "understood": bool(result.get("understood", True)),
                "requested_unsupported_place": bool(result.get("requested_unsupported_place", False)),
            }

    # Shouldn't happen with tool_choice forcing this exact tool, but don't
    # ever silently pretend we understood something we didn't.
    return {"countries": [], "min_avg_temp_c": None, "understood": False, "requested_unsupported_place": False}


def resolve_destinations(query: str, airports: list[dict], travel_month: int):
    """Turn a free-text query into (destination_airport_codes, intent).

    An empty query means "anywhere" (every curated airport) — no Claude call
    made. A non-empty query Claude doesn't recognize as any kind of travel
    preference also falls back to "anywhere". A recognized preference that
    matches zero airports (e.g. a country outside this app's network, or an
    unreachable temperature) returns an empty list on purpose — the caller
    should show "no matches", not silently search everywhere.
    """
    query = (query or "").strip()
    if not query:
        return [a["code"] for a in airports], {
            "countries": [], "min_avg_temp_c": None, "understood": False, "requested_unsupported_place": False,
        }

    countries = sorted({a["country"] for a in airports})
    intent = parse_travel_query(query, countries)

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
