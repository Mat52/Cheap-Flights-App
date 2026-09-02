"""Standalone price-watch daemon — a second, independent app from the
Flask search UI. Checks a small, hand-picked list of specific flights
(app/watchlist.json) and sends a Telegram message to your phone the moment
any of their prices change (up or down) from what was last seen.

Two ways to run it, two "last seen price" backends:

- Locally, forever (`python price_watcher.py`): loops every
  WATCHER_INTERVAL_SECONDS (default 3 min), reusing the shared Postgres
  `flights` table as its price history (PostgresPriceStore) — the same
  history the web UI's own searches build, no separate state needed. See
  the README's "Price Watcher" section for running this as a real 24/7
  background service via launchd.
- One-shot, for GitHub Actions (`python price_watcher.py --once`): does a
  single check and exits, using a small JSON file (JsonFilePriceStore,
  price_history.json) instead of Postgres — GitHub's runners can't reach
  your local database. Keys are hashed (origin+destination+date), not
  plaintext, specifically because this file is meant to be committed back
  to the repo by the workflow after each run: on a public repo, a
  plaintext key would publish your actual travel dates in the commit
  history. See .github/workflows/price_watcher.yml and the README.

Each watchlist entry needs origin/destination/date; "label" and "airline"
are optional. Without "airline", a check is "whatever's cheapest overall"
(any carrier, any number of stops) — the same thing the web UI's search
does. With "airline" (e.g. "Ryanair"), it scans the full results list
instead of just the top card and reports that airline's own price, and by
default (direct_only, true unless set to false) only counts a flight with
no connections — see search_flight_google_for_airline()'s docstring for
why: a connecting itinerary on a different carrier can undercut a budget
airline's own direct flight and still show up first as "cheapest overall".

⚠️ This hits Google Flights for the exact same handful of queries on a
fixed schedule, forever — a much more bot-like traffic pattern than the
one-off searches the web UI makes, and a real ban-risk trade-off for
however "responsive" you want the check interval to be. There's no
special evasion here (beyond the jitter on the local-loop path) — see the
env var docs below before cranking WATCHER_INTERVAL_SECONDS down further,
and note GitHub Actions itself enforces a 5-minute floor on schedules
regardless (see the README).
"""
import asyncio
import hashlib
import json
import os
import random
import signal
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
from playwright.async_api import async_playwright

import database
from core.googleflights import search_flight_google, search_flight_google_for_airline, warm_up_cookies
from core.telegram import wyslij_telegram

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# How often the *local, looping* mode re-checks every watched flight —
# irrelevant to --once, which is invoked externally by GitHub's own cron.
# See the ban-risk warning in the module docstring before lowering it;
# raising it is always safe.
WATCHER_INTERVAL_SECONDS = int(os.getenv("WATCHER_INTERVAL_SECONDS", "180"))
# +/- this many seconds of random jitter around the interval (local mode
# only), so the schedule isn't perfectly periodic.
WATCHER_JITTER_SECONDS = int(os.getenv("WATCHER_JITTER_SECONDS", "20"))
# Pause between individual watched flights within one check cycle — keeps
# a watchlist of a few flights from all hitting Google in the same instant.
WATCHER_PER_FLIGHT_DELAY_SECONDS = 2

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_PATH = os.path.join(APP_DIR, "watchlist.json")
PRICE_HISTORY_PATH = os.path.join(APP_DIR, "price_history.json")

_shutdown = False


def _log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def _handle_signal(signum, frame):
    global _shutdown
    _log("🛑 Otrzymano sygnał zatrzymania — kończę po bieżącym cyklu…")
    _shutdown = True


def load_watchlist():
    if not os.path.exists(WATCHLIST_PATH):
        _log(f"⚠️ Brak {WATCHLIST_PATH} — skopiuj watchlist.example.json i dodaj swoje loty.")
        return []
    with open(WATCHLIST_PATH, encoding="utf-8") as f:
        entries = json.load(f)
    for e in entries:
        for field in ("origin", "destination", "date"):
            if field not in e:
                raise ValueError(f"Wpis w watchlist.json bez pola '{field}': {e}")
        e["origin"] = e["origin"].strip().upper()
        e["destination"] = e["destination"].strip().upper()
    return entries


def describe(entry):
    return entry.get("label") or f"{entry['origin']} → {entry['destination']}"


class PostgresPriceStore:
    """Price history backed by the shared `flights` table — used by the
    local, looping mode. get_last_price/save_price are sync (psycopg2);
    check_once() runs both through asyncio.to_thread."""

    def get_last_price(self, origin, destination, date):
        return database.get_last_price(origin, destination, date)

    def save_price(self, result):
        database.save_flight_result(result)

    def flush(self):
        pass  # nothing to do — every write already went straight to Postgres


class JsonFilePriceStore:
    """Price history as a small local JSON file — used by --once, for
    environments with no reachable Postgres (GitHub Actions runners).
    Keys are a short hash of (origin, destination, date), not the
    plaintext route: this file is meant to be committed back to the repo
    after each run, and on a public repo a plaintext key would publish
    your actual travel dates in the commit history. flush() must be
    called once after all checks in a run to persist changes to disk.
    """

    def __init__(self, path):
        self.path = path
        self._data = self._load()
        self._dirty = False

    def _load(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _key(origin, destination, date):
        raw = f"{origin}|{destination}|{date}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def get_last_price(self, origin, destination, date):
        entry = self._data.get(self._key(origin, destination, date))
        return entry["price"] if entry else None

    def save_price(self, result):
        key = self._key(result["origin"], result["destination"], result["date"])
        self._data[key] = {
            "price": result["price"],
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._dirty = True

    def flush(self):
        if not self._dirty:
            return
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=1, sort_keys=True)
        self._dirty = False


def notify_price_change(entry, previous_price, new_result):
    direction = "📈 wzrosła" if new_result["price"] > previous_price else "📉 spadła"
    diff = round(new_result["price"] - previous_price, 2)
    message = (
        f"💰 Zmiana ceny — {describe(entry)}\n"
        f"{new_result['origin']} → {new_result['destination']} | {new_result['date']}\n"
        f"{new_result['Airline']} | {new_result['departure']}–{new_result['arrival']}\n"
        f"{previous_price} PLN → <b>{new_result['price']} PLN</b> ({direction}, {diff:+.2f} PLN)"
    )
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        wyslij_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
        _log(f"📨 Wysłano powiadomienie: {describe(entry)}: {previous_price} -> {new_result['price']} PLN")
    else:
        _log(
            "⚠️ Zmiana ceny wykryta, ale TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID nie są "
            f"skonfigurowane (patrz .env.example) — powiadomienie NIE zostało wysłane: {message}"
        )


async def check_once(watchlist, price_store):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            context.set_default_timeout(8000)
            await warm_up_cookies(context)

            for entry in watchlist:
                page = await context.new_page()
                try:
                    if entry.get("airline"):
                        # Specific-airline watch, e.g. a budget carrier's
                        # own direct flight — not just whatever's cheapest
                        # overall (which can be a connection on a different
                        # airline entirely; see search_flight_google_for_airline's
                        # docstring for a real example this was built for).
                        result = await search_flight_google_for_airline(
                            page, entry["origin"], entry["destination"], entry["date"],
                            entry["airline"], direct_only=entry.get("direct_only", True),
                        )
                    else:
                        result = await search_flight_google(page, entry["origin"], entry["destination"], entry["date"])
                finally:
                    await page.close()

                if not result:
                    _log(f"⚠️ Nie udało się sprawdzić: {describe(entry)} ({entry['date']})")
                    await asyncio.sleep(WATCHER_PER_FLIGHT_DELAY_SECONDS)
                    continue

                previous_price = await asyncio.to_thread(
                    price_store.get_last_price, entry["origin"], entry["destination"], entry["date"]
                )
                await asyncio.to_thread(price_store.save_price, result)

                if previous_price is None:
                    _log(f"👀 Pierwszy odczyt: {describe(entry)} = {result['price']} PLN")
                elif previous_price != result["price"]:
                    notify_price_change(entry, previous_price, result)
                else:
                    _log(f"➖ Bez zmian: {describe(entry)} = {result['price']} PLN")

                await asyncio.sleep(WATCHER_PER_FLIGHT_DELAY_SECONDS)
        finally:
            await browser.close()
            price_store.flush()


def run_once():
    """Single check-and-exit, for an external scheduler (GitHub Actions).
    Uses JsonFilePriceStore, not Postgres — see the module docstring."""
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        _log("⚠️ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID nie są skonfigurowane — zmiany cen będą tylko logowane, nie wysyłane na telefon.")

    watchlist = load_watchlist()
    if not watchlist:
        _log("⚠️ Watchlist jest pusta — nic do sprawdzenia.")
        sys.exit(1)

    _log(f"🔎 Jednorazowe sprawdzenie {len(watchlist)} lotów (--once): " + ", ".join(describe(e) for e in watchlist))
    price_store = JsonFilePriceStore(PRICE_HISTORY_PATH)
    asyncio.run(check_once(watchlist, price_store))
    _log("✅ Gotowe.")


def main():
    try:
        database.init_db()
    except Exception as e:
        _log(f"⚠️ Baza danych niedostępna przy starcie: {e}")

    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        _log("⚠️ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID nie są skonfigurowane — zmiany cen będą tylko logowane, nie wysyłane na telefon.")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    watchlist = load_watchlist()
    if not watchlist:
        _log("⚠️ Watchlist jest pusta — nic do obserwowania. Dodaj loty do watchlist.json i uruchom ponownie.")
        sys.exit(1)

    _log(f"🚀 Start — obserwuję {len(watchlist)} lotów co ~{WATCHER_INTERVAL_SECONDS}s: " + ", ".join(describe(e) for e in watchlist))
    price_store = PostgresPriceStore()

    while not _shutdown:
        cycle_start = time.time()
        try:
            asyncio.run(check_once(watchlist, price_store))
        except Exception as e:
            _log(f"❌ Błąd w cyklu sprawdzania: {e}")

        if _shutdown:
            break

        elapsed = time.time() - cycle_start
        jitter = random.uniform(-WATCHER_JITTER_SECONDS, WATCHER_JITTER_SECONDS)
        sleep_for = max(10, WATCHER_INTERVAL_SECONDS - elapsed + jitter)
        _log(f"😴 Cykl zajął {elapsed:.0f}s, następny za {sleep_for:.0f}s")
        for _ in range(int(sleep_for)):
            if _shutdown:
                break
            time.sleep(1)

    _log("👋 Zatrzymano.")


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        main()
