"""Standalone price-watch daemon — a second, independent app from the
Flask search UI. Runs forever: every WATCHER_INTERVAL_SECONDS (default 3
minutes), it checks a small, hand-picked list of specific flights
(app/watchlist.json) and sends a Telegram message to your phone the moment
any of their prices change (up or down) from what was last seen.

It reuses this repo's existing scraper (core.googleflights), Telegram
sender (core.telegram) and Postgres layer (database) as plain libraries —
it does not touch or depend on webapp.py, and can run with or without the
Flask app up. "Last seen price" is just the most recent row already in the
shared `flights` table for that exact leg (database.get_last_price), so no
separate state file is needed: every check both compares against and then
extends the same history the web UI's searches already build.

Usage:
    venv/bin/python price_watcher.py
Runs in the foreground until killed — see docs/price-watcher.md (or the
README) for running it as a real 24/7 background service via launchd.

⚠️ This hits Google Flights for the exact same handful of queries on a
fixed schedule, forever — a much more bot-like traffic pattern than the
one-off searches the web UI makes, and a real ban-risk trade-off for
however "responsive" you want WATCHER_INTERVAL_SECONDS to be. There's no
special evasion here, just a small random jitter so the interval isn't
perfectly periodic — see the env var docs below before cranking the
interval down further.
"""
import asyncio
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
from core.googleflights import search_flight_google, warm_up_cookies
from core.telegram import wyslij_telegram

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# How often to re-check every watched flight. Default matches what was
# asked for (3 min) — see the ban-risk warning in the module docstring
# before lowering it further; raising it is always safe.
WATCHER_INTERVAL_SECONDS = int(os.getenv("WATCHER_INTERVAL_SECONDS", "180"))
# +/- this many seconds of random jitter around the interval, so the
# schedule isn't perfectly periodic (a small, honest mitigation — not a
# guarantee against bot detection).
WATCHER_JITTER_SECONDS = int(os.getenv("WATCHER_JITTER_SECONDS", "20"))
# Pause between individual watched flights within one check cycle — keeps
# a watchlist of a few flights from all hitting Google in the same instant.
WATCHER_PER_FLIGHT_DELAY_SECONDS = 2

WATCHLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")

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


async def check_once(watchlist):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            context.set_default_timeout(8000)
            await warm_up_cookies(context)

            for entry in watchlist:
                page = await context.new_page()
                try:
                    result = await search_flight_google(page, entry["origin"], entry["destination"], entry["date"])
                finally:
                    await page.close()

                if not result:
                    _log(f"⚠️ Nie udało się sprawdzić: {describe(entry)} ({entry['date']})")
                    await asyncio.sleep(WATCHER_PER_FLIGHT_DELAY_SECONDS)
                    continue

                previous_price = await asyncio.to_thread(
                    database.get_last_price, entry["origin"], entry["destination"], entry["date"]
                )
                await asyncio.to_thread(database.save_flight_result, result)

                if previous_price is None:
                    _log(f"👀 Pierwszy odczyt: {describe(entry)} = {result['price']} PLN")
                elif previous_price != result["price"]:
                    notify_price_change(entry, previous_price, result)
                else:
                    _log(f"➖ Bez zmian: {describe(entry)} = {result['price']} PLN")

                await asyncio.sleep(WATCHER_PER_FLIGHT_DELAY_SECONDS)
        finally:
            await browser.close()


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

    while not _shutdown:
        cycle_start = time.time()
        try:
            asyncio.run(check_once(watchlist))
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
    main()
