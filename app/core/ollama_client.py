"""Shared plumbing for calling the local Ollama model with a JSON-schema
constrained response — used by both travel_intent.py (destinations) and
date_intent.py (dates).

Every caller of call_ollama_json() is expected to independently verify
whatever the model returns rather than trust it outright — see
travel_intent.py's module docstring for why (a small local model has been
observed both hallucinating values and parroting prompt examples back).
This module only handles getting a JSON object out of Ollama; it makes no
claim about whether that JSON is actually correct.
"""
import json
import os

import requests

# http://host.docker.internal:11434 if the web app runs in Docker and Ollama
# runs on the host — see docker-compose.yml.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
REQUEST_TIMEOUT_SECONDS = 60


def call_ollama_json(prompt: str, schema: dict) -> dict:
    """Send a single user-turn prompt to Ollama, constrained to `schema`
    (a JSON Schema object), and return the parsed response dict.

    Raises RuntimeError with a Polish, user-facing message on any failure —
    Ollama unreachable, the model not pulled, a timeout, or a response that
    isn't valid JSON — so callers can surface it the same way a validation
    error is surfaced, instead of guessing a result.
    """
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": schema,
                "options": {"temperature": 0, "num_predict": 200},
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            "Nie można połączyć się z Ollama (http://localhost:11434) — uruchom `ollama serve` "
            "(albo `brew services start ollama`) i upewnij się, że model jest pobrany: "
            f"`ollama pull {OLLAMA_MODEL}`."
        ) from e
    except requests.exceptions.Timeout as e:
        raise RuntimeError("Ollama nie odpowiedziało w rozsądnym czasie — spróbuj ponownie.") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Błąd zapytania do Ollama: {e}") from e

    content = response.json()["message"]["content"]
    try:
        return json.loads(content)
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Ollama zwróciło nieoczekiwaną odpowiedź: {e}") from e
