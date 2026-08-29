import asyncio
import os

from dotenv import load_dotenv
from flask import Flask, render_template, request
from playwright.async_api import async_playwright

import database
from core.search import run_search, znajdz_polaczenia_dwustronne
from core.telegram import wyslij_telegram
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
    "destinations": "BCN, GRO",
    "grupy_baz": "KRK, KTW",
    "grupy_destynacji": "BCN, GRO",
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


@app.route("/", methods=["GET", "POST"])
def index():
    form = dict(DEFAULTS)
    results = None
    offers = None
    error = None
    telegram_sent = False

    if request.method == "GET":
        # lets a link (e.g. "no saved results — search live instead" on
        # /saved) pre-fill the airport fields without auto-submitting a search
        for key in ("origins", "destinations", "grupy_baz", "grupy_destynacji"):
            if request.args.get(key):
                form[key] = request.args[key]

    if request.method == "POST":
        form.update({
            "origins": request.form.get("origins", ""),
            "destinations": request.form.get("destinations", ""),
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

        try:
            origins = parse_codes(form["origins"])
            destinations = parse_codes(form["destinations"])
            if not origins:
                raise ValueError("Podaj przynajmniej jedno lotnisko wylotu.")
            if not destinations:
                raise ValueError("Podaj przynajmniej jedno lotnisko docelowe.")
            if not form["departure_start"] or not form["departure_end"]:
                raise ValueError("Podaj zakres dat wylotu.")
            if not form["return_start"] or not form["return_end"]:
                raise ValueError("Podaj zakres dat powrotu.")

            params = {
                "origins": origins,
                "destinations": destinations,
                "dates_departure": generate_dates(form["departure_start"], form["departure_end"]),
                "dates_back": generate_dates(form["return_start"], form["return_end"]),
                "grupy_baz": parse_groups(form["grupy_baz"]),
                "grupy_destynacji": parse_groups(form["grupy_destynacji"]),
                "min_days": int(form["min_days"]),
                "max_days": int(form["max_days"]),
            }
            price_threshold = float(form["price_threshold"])

            def persist(flight):
                try:
                    database.save_flight_result(flight)
                except Exception as e:
                    print(f"⚠️ Nie udało się zapisać lotu do bazy: {e}")

            cache_minutes = CACHE_MAX_AGE_MINUTES if form["use_cache"] else 0

            async def do_search():
                # A fresh Playwright driver per request, not a shared/cached
                # one: the async API's dispatcher is bound to the event loop
                # that started it, which doesn't survive being reused from a
                # later, separate asyncio.run() call. launch_browser is only
                # actually invoked by run_search if some leg isn't already
                # covered by the cache.
                async with async_playwright() as p:
                    async def launch_browser():
                        return await p.chromium.launch(headless=True)

                    return await run_search(
                        launch_browser,
                        params,
                        on_result=persist,
                        concurrency=SCRAPE_CONCURRENCY,
                        cache_max_age_minutes=cache_minutes,
                    )

            results, offers = asyncio.run(do_search())

            good_offers = [o for o in offers if o["cena"] < price_threshold]
            if good_offers and form["notify_telegram"]:
                if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                    wyslij_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, format_offer_message(good_offers))
                    telegram_sent = True
                else:
                    error = (
                        "Znaleziono okazje, ale TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID nie są "
                        "skonfigurowane (patrz .env.example) — powiadomienie nie zostało wysłane."
                    )

        except ValueError as e:
            error = str(e)
        except Exception as e:
            error = f"Błąd wyszukiwania: {e}"

    good_price_threshold = None
    if request.method == "POST" and not error:
        try:
            good_price_threshold = float(form["price_threshold"])
        except ValueError:
            good_price_threshold = None

    return render_template(
        "index.html",
        form=form,
        results=results,
        offers=offers,
        price_threshold=good_price_threshold,
        error=error,
        telegram_sent=telegram_sent,
        telegram_configured=bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
    )


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
    # threaded=False: one browser session (and its own asyncio.run() event
    # loop) per process at a time — requests are still handled one at a
    # time; the concurrency added in core.search happens *within* a single
    # request's search, across its many legs, not across separate requests.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False, threaded=False)
