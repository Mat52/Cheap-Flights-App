# ✈️ Cheap Flights App

A small web app for hunting cheap round-trip flights on **Google Flights**. Type in your airports, date ranges and price threshold on the page, hit search, and it scrapes, pairs up outbound/return legs into round-trip offers, saves what it finds to Postgres, and (optionally) pings you on Telegram for anything under your price threshold.

---

## 📦 Features
- Scrapes **Google Flights** for one-way legs across any set of origins × destinations × dates you enter, scraping several legs concurrently instead of one at a time (`SCRAPE_CONCURRENCY`)
- Reuses recently-scraped legs straight from Postgres instead of re-scraping them (`CACHE_MAX_AGE_MINUTES`, toggle per-search with "Użyj cache") — a fully-cached repeat search doesn't open a browser at all
- Pick airports without knowing IATA codes: a checkbox list of the ~160 airports most commonly served by Ryanair/Wizz Air/easyJet in Europe (+ nearby leisure destinations), grouped by country, with a live map and a search filter (Polish city names included, e.g. "Warszawa", "Rzym") — or type a code by hand if you know one they don't cover
- **🌍 Dokądkolwiek** mode: pick your origin(s), skip picking destinations, and it scans every airport on the list to find the cheapest deal anywhere (narrow the dates for this — see Known limitations)
- Pairs legs into round-trip offers, with optional "these airports count as the same region" grouping (e.g. flew into BCN, fine to fly back from GRO)
- Persists every scraped flight to Postgres (best-effort — search still works if the DB is unreachable)
- Sends a Telegram alert for offers under your price threshold, if configured
- Everything is entered live on the page — no more editing Python config files per trip

---

## 🔑 Configuration

Copy `.env.example` to `.env` at the repo root and fill it in:

```bash
cp .env.example .env
```

- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — optional. Create a bot via [@BotFather](https://t.me/BotFather), then message it and hit `https://api.telegram.org/bot<token>/getUpdates` to find your chat id. Without these, search still works, alerts are just skipped.
- `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` — Postgres connection. Defaults match `docker-compose.yml`'s `db` service.
- `PORT` — port the web UI listens on (default `5000`).
- `SCRAPE_CONCURRENCY` — how many Google Flights pages to scrape at once per search (default `5`). Higher is faster but pushes harder against Google's own rate limiting/bot detection.
- `CACHE_MAX_AGE_MINUTES` — how fresh a previously-scraped leg has to be to reuse it instead of scraping again (default `30`); `0` always scrapes live. Per-search override via the "Użyj cache" checkbox on the page.

**Never commit `.env`** — it's gitignored.

---

## 🚀 Quick Start (Local)

### 1. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium
```

### 3. Configure
```bash
cp .env.example .env   # then edit .env if you want Telegram alerts / a non-default DB
```

### 4. Run the web app
```bash
cd app
python webapp.py
```
Open **http://localhost:5000**, fill in the form and search. Postgres persistence is optional locally — if nothing is listening on `DB_HOST:DB_PORT`, the app logs a warning and keeps working without saving to the DB.

---

## 🐳 Run with Docker

```bash
docker-compose up --build
```
Docker Compose reads `.env` from the repo root automatically, so make sure it exists first. This brings up:
- **web** — the Flask app + scraper at `http://localhost:5000`
- **db** — Postgres, storing scraped flights
- **pgadmin** — at `http://localhost:8080` (login: `admin@admin.com` / `admin`) to browse the `flights` table

---

## 📂 Project Structure
```
Cheap-Flights-App/
│
├── app/
│   ├── webapp.py               # Flask app: search form + results
│   ├── templates/index.html    # the search page
│   ├── core/
│   │   ├── googleflights.py    # Playwright scraper for one Google Flights leg
│   │   ├── search.py           # scans routes/dates, pairs legs into round-trip offers
│   │   ├── telegram.py         # Telegram sender
│   │   └── utils.py            # generate_dates() helper
│   └── database.py             # Postgres persistence (init_db / save_flight_result)
│
├── docker/
│   ├── Dockerfile
│   └── entrypoint.sh
├── docker-compose.yml          # web + Postgres + pgAdmin
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## ⚠️ Known limitations
- The scraper is tightly coupled to the **Polish-locale Google Flights UI** (button text, CSS classes) and short Playwright timeouts — a UI or locale change upstream can silently break it, and errors are logged as "no results found" rather than distinguished from real empty results.
- A search runs synchronously in the request — the page waits for the whole scrape before showing results, with no progress indicator beyond a spinner. Legs are now scraped concurrently (`SCRAPE_CONCURRENCY`, default 5 at once) and a leg already scraped within `CACHE_MAX_AGE_MINUTES` is reused from Postgres instead of re-scraped, which cuts a lot of the wait for wide searches and for repeat/overlapping ones — but a wide first-time search (many airports/dates, or "🌍 Dokądkolwiek" against all 161 curated airports) can still take a while. Narrow the date range for wide searches.
- Raising `SCRAPE_CONCURRENCY` too high risks Google rate-limiting or bot-detecting the scraper sooner than the current sequential-ish pace does — there's no backoff/retry on that yet, a blocked leg just comes back as "no results found" like any other scrape failure.
- There's no automated test suite yet.

---

## 📜 License
MIT License
