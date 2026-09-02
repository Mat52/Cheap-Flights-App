import asyncio
import os
import threading
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from playwright.async_api import async_playwright

import database
from core.airports import load_airports
from core.date_intent import resolve_dates
from core.search import build_legs, run_search, znajdz_polaczenia_dwustronne
from core.telegram import wyslij_telegram
from core.travel_intent import resolve_destinations
from core.utils import generate_dates

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# How many Google Flights pages to scrape at once (raise cautiously — too
# high risks Google's own rate limiting/bot detection kicking in sooner).
SCRAPE_CONCURRENCY = int(os.getenv("SCRAPE_CONCURRENCY", "5"))
# How fresh a previously-scraped leg has to be to reuse it instead of
# scraping again; 0 disables the cache outright.
CACHE_MAX_AGE_MINUTES = int(os.getenv("CACHE_MAX_AGE_MINUTES", "30"))

app = Flask(__name__)

try:
    database.init_db()
except Exception as e:
    print(f"⚠️ Baza danych niedostępna przy starcie: {e}")

# In-memory registry of live/finished searches, so the page can show a real
# progress bar instead of hanging unresponsively for the whole scrape: a
# search runs in a background thread (see run_search_job) while the browser
# polls /search-status/<id>. Personal-use scale — an in-memory dict is fine,
# no need for a real job queue. JOBS_LOCK guards every read/write since the
# background thread and request-handling threads touch it concurrently.
JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_TTL_SECONDS = 3600  # stale jobs are pruned on the next search, not live


def _prune_old_jobs():
    cutoff = time.time() - JOB_TTL_SECONDS
    with JOBS_LOCK:
        for sid in [sid for sid, job in JOBS.items() if job["created_at"] < cutoff]:
            del JOBS[sid]


def parse_codes(raw: str):
    """'KRK, KTW' or one-per-line -> ['KRK', 'KTW']"""
    return [c.strip().upper() for c in raw.replace("\n", ",").split(",") if c.strip()]


def parse_groups(raw: str):
    """One group per line, comma-separated codes -> [['BCN','GRO'], ['PFO','LCA']]"""
    groups = []
    for line in raw.splitlines():
        codes = [c.strip().upper() for c in line.split(",") if c.strip()]
        if codes:
            groups.append(codes)
    return groups


DEFAULTS = {
    "origins": "KRK, KTW",
    "travel_query": "",
    "anywhere_destinations": False,
    "date_query": "",
    "grupy_baz": "KRK, KTW",
    "grupy_destynacji": "",
    "departure_start": "",
    "departure_end": "",
    "return_start": "",
    "return_end": "",
    "min_days": "2",
    "max_days": "5",
    "price_threshold": "500",
    "notify_telegram": True,
    "use_cache": True,
}


def describe_intent(intent, query):
    """Human-readable (Polish) summary of what the AI destination search
    understood from `query`, shown back to the user next to the results so
    a wrong/partial interpretation is obvious rather than silent."""
    if not query.strip():
        return "🌍 Brak zapytania — przeszukano wszystkie lotniska z listy."
    if not intent["understood"]:
        return "🤔 Nie rozpoznano preferencji w zapytaniu — przeszukano wszystkie lotniska z listy."
    parts = []
    if intent["countries"]:
        parts.append("kraje: " + ", ".join(intent["countries"]))
    if intent["min_avg_temp_c"] is not None:
        parts.append(f"min. śr. temperatura: {intent['min_avg_temp_c']}°C")
    if not parts:
        return "🌍 Nie rozpoznano konkretnej preferencji — przeszukano wszystkie lotniska z listy."
    return "✅ Zrozumiano: " + " | ".join(parts)


def format_offer_message(offers):
    msg = "📋 <b>ZNALEZIONE OKAZJE TAM I Z POWROTEM:</b>\n"
    for o in offers:
        tam, powrot = o["tam"], o["powrot"]
        msg += (
            f"\n🛫 {tam['origin']} -> {tam['destination']} | {tam['date']} | {tam['Airline']} | {tam['departure']} | {tam['arrival']} | {tam['price']} PLN"
            f"\n🛬 {powrot['origin']} -> {powrot['destination']} | {powrot['date']} | {powrot['Airline']} | {powrot['departure']} | {powrot['arrival']} | {powrot['price']} PLN"
            f"\n💰 <b>Suma:</b> {o['cena']} PLN | <i>Pobyt:</i> {o['pobyt']} dni\n"
        )
    return msg


def run_search_job(search_id, form):
    """Runs entirely in a background thread, started by index()'s POST
    handler right after the cheap validation passes — this is everything
    that used to block the request: the AI destination-query call, then the
    scrape itself. Progress is reported into JOBS[search_id] as it happens
    so /search-status/<id> has something live to report to the page.
    """
    def fail(message):
        with JOBS_LOCK:
            JOBS[search_id].update(status="done", error=message)

    try:
        # Dates: the free-text "Kiedy?" query, when given, takes priority
        # over the exact date pickers — AI-resolved into concrete dates (and
        # possibly its own stay-length preference) by resolve_dates(), which
        # falls back to None if it can't recognize a month in the query at
        # all (nothing worth overriding manual dates with).
        date_result = None
        if form["date_query"].strip():
            try:
                date_result = resolve_dates(form["date_query"])
            except RuntimeError as e:
                return fail(str(e))
            if date_result:
                with JOBS_LOCK:
                    JOBS[search_id]["date_intent_summary"] = date_result["summary"]

        if date_result:
            dates_departure = date_result["dates_departure"]
            dates_back = date_result["dates_back"]
            min_days = date_result["min_days"] if date_result["min_days"] is not None else int(form["min_days"])
            max_days = date_result["max_days"] if date_result["max_days"] is not None else int(form["max_days"])
        elif form["departure_start"] and form["departure_end"] and form["return_start"] and form["return_end"]:
            dates_departure = generate_dates(form["departure_start"], form["departure_end"])
            dates_back = generate_dates(form["return_start"], form["return_end"])
            min_days = int(form["min_days"])
            max_days = int(form["max_days"])
        else:
            return fail(
                f"Nie rozpoznano dat z zapytania „{form['date_query']}”. "
                "Podaj dokładne daty w polach powyżej albo doprecyzuj zapytanie (np. podaj nazwę miesiąca)."
            )

        if not dates_departure or not dates_back:
            return fail("Brak dat pasujących do zapytania — spróbuj innego miesiąca albo podaj dokładne daty.")

        if form["anywhere_destinations"]:
            # Deterministic, no Ollama call at all — bypasses the AI query
            # entirely rather than relying on it to correctly recognize
            # "no preference" as a concept. That reliance was the actual
            # bug this checkbox exists to route around: typing the word
            # "gdziekolwiek" ("anywhere") into the free-text field still
            # sends it to the model like any other query, and it can be
            # (and was, in testing) misread as a specific, unsupported
            # place instead of "no preference" — this checkbox can't
            # misfire that way because it never asks the model anything.
            destinations = [a["code"] for a in load_airports()]
            intent_summary = "🌍 Dokądkolwiek — przeszukano wszystkie lotniska z listy (bez pytania AI)."
            with JOBS_LOCK:
                JOBS[search_id]["intent_summary"] = intent_summary
        else:
            departure_month = datetime.strptime(dates_departure[0], "%Y-%m-%d").month
            try:
                destinations, intent = resolve_destinations(form["travel_query"], load_airports(), departure_month)
            except RuntimeError as e:
                # Ollama itself failed (not running, model missing, ...)
                return fail(str(e))

            intent_summary = describe_intent(intent, form["travel_query"])
            with JOBS_LOCK:
                JOBS[search_id]["intent_summary"] = intent_summary

        if not destinations:
            return fail(
                f"Brak lotnisk pasujących do zapytania „{form['travel_query']}”. "
                "Spróbuj innego kraju/regionu albo zostaw pole puste, żeby przeszukać wszystko."
            )

        params = {
            "origins": parse_codes(form["origins"]),
            "destinations": destinations,
            "dates_departure": dates_departure,
            "dates_back": dates_back,
            "grupy_baz": parse_groups(form["grupy_baz"]),
            "grupy_destynacji": parse_groups(form["grupy_destynacji"]),
            "min_days": min_days,
            "max_days": max_days,
        }
        price_threshold = float(form["price_threshold"])
        total_legs = len(build_legs(params))

        with JOBS_LOCK:
            JOBS[search_id].update(status="scraping", total=total_legs)

        def persist(flight):
            try:
                database.save_flight_result(flight)
            except Exception as e:
                print(f"⚠️ Nie udało się zapisać lotu do bazy: {e}")

        def bump_progress():
            with JOBS_LOCK:
                JOBS[search_id]["done"] += 1

        cache_minutes = CACHE_MAX_AGE_MINUTES if form["use_cache"] else 0

        async def do_search():
            # A fresh Playwright driver per search, not a shared/cached one:
            # the async API's dispatcher is bound to the event loop that
            # started it. launch_browser is only actually invoked by
            # run_search if some leg isn't already covered by the cache.
            async with async_playwright() as p:
                async def launch_browser():
                    return await p.chromium.launch(headless=True)

                return await run_search(
                    launch_browser,
                    params,
                    on_result=persist,
                    on_progress=bump_progress,
                    concurrency=SCRAPE_CONCURRENCY,
                    cache_max_age_minutes=cache_minutes,
                )

        results, offers = asyncio.run(do_search())

        good_offers = [o for o in offers if o["cena"] < price_threshold]
        telegram_sent = False
        error = None
        if good_offers and form["notify_telegram"]:
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                wyslij_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, format_offer_message(good_offers))
                telegram_sent = True
            else:
                error = (
                    "Znaleziono okazje, ale TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID nie są "
                    "skonfigurowane (patrz .env.example) — powiadomienie nie zostało wysłane."
                )

        with JOBS_LOCK:
            JOBS[search_id].update(
                status="done", results=results, offers=offers, telegram_sent=telegram_sent, error=error,
            )

    except ValueError as e:
        fail(str(e))
    except Exception as e:
        fail(f"Błąd wyszukiwania: {e}")


@app.route("/", methods=["GET", "POST"])
def index():
    form = dict(DEFAULTS)

    if request.method == "GET":
        # lets a link (e.g. "no saved results — search live instead" on
        # /saved) pre-fill the airport fields without auto-submitting a search
        for key in ("origins", "travel_query", "date_query", "grupy_baz", "grupy_destynacji"):
            if request.args.get(key):
                form[key] = request.args[key]
        return render_template(
            "index.html", form=form, results=None, offers=None, price_threshold=None,
            error=None, telegram_sent=False, telegram_configured=bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
            intent_summary=None, date_intent_summary=None,
        )

    form.update({
        "origins": request.form.get("origins", ""),
        "travel_query": request.form.get("travel_query", ""),
        "anywhere_destinations": request.form.get("anywhere_destinations") == "on",
        "date_query": request.form.get("date_query", ""),
        "grupy_baz": request.form.get("grupy_baz", ""),
        "grupy_destynacji": request.form.get("grupy_destynacji", ""),
        "departure_start": request.form.get("departure_start", ""),
        "departure_end": request.form.get("departure_end", ""),
        "return_start": request.form.get("return_start", ""),
        "return_end": request.form.get("return_end", ""),
        "min_days": request.form.get("min_days", DEFAULTS["min_days"]),
        "max_days": request.form.get("max_days", DEFAULTS["max_days"]),
        "price_threshold": request.form.get("price_threshold", DEFAULTS["price_threshold"]),
        "notify_telegram": request.form.get("notify_telegram") == "on",
        "use_cache": request.form.get("use_cache") == "on",
    })

    # Cheap, synchronous checks only — instant feedback on the same page,
    # same as before. Everything slow (the AI query, the scrape itself)
    # moves into a background thread so the page never just sits frozen.
    # A filled-in "Kiedy?" query stands in for the exact date pickers, so
    # they're only required when it's empty.
    has_date_query = bool(form["date_query"].strip())
    error = None
    if not parse_codes(form["origins"]):
        error = "Podaj przynajmniej jedno lotnisko wylotu."
    elif not has_date_query and (not form["departure_start"] or not form["departure_end"]):
        error = "Podaj zakres dat wylotu (albo opisz je w polu „Kiedy?”)."
    elif not has_date_query and (not form["return_start"] or not form["return_end"]):
        error = "Podaj zakres dat powrotu (albo opisz je w polu „Kiedy?”)."
    if error:
        return render_template(
            "index.html", form=form, results=None, offers=None, price_threshold=None,
            error=error, telegram_sent=False, telegram_configured=bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
            intent_summary=None, date_intent_summary=None,
        )

    _prune_old_jobs()
    search_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[search_id] = {
            "status": "resolving", "done": 0, "total": 0, "error": None,
            "results": None, "offers": None, "intent_summary": None, "date_intent_summary": None,
            "telegram_sent": False, "form": dict(form), "created_at": time.time(),
        }
    threading.Thread(target=run_search_job, args=(search_id, form), daemon=True).start()
    return redirect(url_for("search_page", search_id=search_id))


@app.route("/search/<search_id>", methods=["GET"])
def search_page(search_id):
    """Shown right after submitting a search: a live progress bar while
    run_search_job works in the background, or — once it's done — the same
    results markup index() used to render directly, now pulled from JOBS."""
    with JOBS_LOCK:
        job = JOBS.get(search_id)
    if not job:
        return redirect(url_for("index"))  # unknown or pruned — start over

    if job["status"] != "done":
        return render_template("searching.html", search_id=search_id)

    try:
        good_price_threshold = float(job["form"]["price_threshold"])
    except (ValueError, KeyError):
        good_price_threshold = None

    return render_template(
        "index.html",
        form=job["form"],
        results=job["results"],
        offers=job["offers"],
        price_threshold=good_price_threshold,
        error=job["error"],
        telegram_sent=job["telegram_sent"],
        telegram_configured=bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        intent_summary=job["intent_summary"],
        date_intent_summary=job["date_intent_summary"],
    )


@app.route("/search-status/<search_id>", methods=["GET"])
def search_status(search_id):
    """Polled by searching.html's JS every ~1s. Kept intentionally tiny —
    just the numbers the progress bar needs — so it stays fast even while
    the background thread is mid-scrape."""
    with JOBS_LOCK:
        job = JOBS.get(search_id)
    if not job:
        return jsonify({"status": "gone"}), 404
    return jsonify({"status": job["status"], "done": job["done"], "total": job["total"]})


SAVED_DEFAULTS = {
    "origins": "",
    "destinations": "",
    "max_price": "",
    "date_from": "",
    "date_to": "",
    "grupy_baz": "",
    "grupy_destynacji": "",
    "min_days": "0",
    "max_days": "365",
}


@app.route("/saved", methods=["GET"])
def saved():
    """Instant search over flights already scraped and saved by past live
    searches — a plain DB read, no browser/Google Flights involved, so this
    is the fastest way to search: no waiting on a live scrape at all."""
    form = {k: request.args.get(k, v) for k, v in SAVED_DEFAULTS.items()}
    results = []
    offers = []
    error = None

    try:
        origins = parse_codes(form["origins"])
        destinations = parse_codes(form["destinations"])
        max_price = float(form["max_price"]) if form["max_price"] else None
        min_days = int(form["min_days"] or 0)
        max_days = int(form["max_days"] or 365)

        results = database.search_flights(
            origins=origins or None,
            destinations=destinations or None,
            max_price=max_price,
            date_from=form["date_from"] or None,
            date_to=form["date_to"] or None,
        )
        offers = znajdz_polaczenia_dwustronne(
            results,
            parse_groups(form["grupy_destynacji"]),
            parse_groups(form["grupy_baz"]),
            min_days,
            max_days,
        )
    except Exception as e:
        error = f"Nie udało się przeszukać zapisanych lotów: {e}"

    return render_template(
        "saved.html",
        form=form,
        results=results,
        offers=offers,
        error=error,
    )


if __name__ == "__main__":
    # threaded=True: the search itself now runs in a background thread
    # (run_search_job), started by index()'s POST handler and polled by
    # /search-status — the dev server needs to serve those polls
    # concurrently with whatever search is running in the background.
    # Personal-use scale: no cap on concurrent searches, each gets its own
    # browser — fine for one or a few people, not meant for real traffic.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False, threaded=True)
