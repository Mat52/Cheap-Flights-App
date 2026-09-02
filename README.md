# ✈️ Cheap Flights App

A small web app for hunting cheap round-trip flights on **Google Flights**. Type in your airports, date ranges and price threshold on the page, hit search, and it scrapes, pairs up outbound/return legs into round-trip offers, saves what it finds to Postgres, and (optionally) pings you on Telegram for anything under your price threshold.

---

## 📦 Features
- Scrapes **Google Flights** for one-way legs across any set of origins × destinations × dates you enter, scraping several legs concurrently instead of one at a time (`SCRAPE_CONCURRENCY`)
- Reuses recently-scraped legs straight from Postgres instead of re-scraping them (`CACHE_MAX_AGE_MINUTES`, toggle per-search with "Użyj cache") — a fully-cached repeat search doesn't open a browser at all
- Pick departure airports without knowing IATA codes: a checkbox list of the ~160 airports most commonly served by Ryanair/Wizz Air/easyJet in Europe (+ nearby leisure destinations), grouped by country, with a search filter (Polish city names included, e.g. "Warszawa", "Rzym") — or type a code by hand if you know one they don't cover
- **AI destination search**: describe where you want to go in plain language ("Hiszpania", "gdziekolwiek gdzie jest cieplej niż 20°C", "Włochy albo Grecja") and a local Ollama model resolves it against the curated airport list — no cloud API, no key, no cost. Country/region names and any temperature preference the model extracts are re-verified in plain Python against the actual query text and against precomputed historical climate normals for the travel month (see "Known limitations" — local models need this safety net) before being trusted. An empty query searches every curated airport, same as the old "🌍 Dokądkolwiek" mode.
- **AI date search**: describe when you want to fly ("weekend we wrześniu", "długi weekend w październiku", "od 10 do 20 września", "tydzień w listopadzie") instead of picking exact date ranges — same local Ollama model, but it only extracts a month/day-range/trip-shape (things worth trusting a language model with); every actual calendar date is generated afterward in plain Python (`core/date_intent.py`), so "weekend" reliably means real Thursday/Friday/Saturday departures paired with Saturday/Sunday/Monday returns, never a model guess at which day of the week a date falls on. Optional — leave it empty and the exact date pickers below work exactly as before.
- Pairs legs into round-trip offers, with optional "these airports count as the same region" grouping (e.g. flew into BCN, fine to fly back from GRO)
- Persists every scraped flight to Postgres (best-effort — search still works if the DB is unreachable)
- Sends a Telegram alert for offers under your price threshold, if configured
- Everything is entered live on the page — no more editing Python config files per trip
- **`price_watcher.py`** — a second, standalone 24/7 app: pick a handful of specific flights, it checks each one every few minutes and Telegrams you the moment a price changes. Runs locally (macOS LaunchAgent) or on GitHub Actions, so it keeps checking even with your own machine off (see "Price Watcher" below)

---

## 🔑 Configuration

Copy `.env.example` to `.env` at the repo root and fill it in:

```bash
cp .env.example .env
```

- `OLLAMA_HOST` / `OLLAMA_MODEL` — used by the "Dokąd chcesz polecieć?" free-text destination search (defaults: `http://localhost:11434`, `llama3.1:8b`). Requires Ollama running locally with that model pulled (see Quick Start); without it, that field only works left empty (searches every curated airport) — a non-empty query fails with a clear error instead of guessing.
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

### 3. Set up Ollama (for the "Dokąd chcesz polecieć?" / "Kiedy chcesz polecieć?" AI search)
```bash
brew install ollama                # macOS; see ollama.com for other platforms
brew services start ollama
ollama pull llama3.1:8b            # ~4.9 GB download
```
Optional — the rest of the app works fine without this, but the free-text destination field only handles an empty query ("anywhere") until Ollama is running with the model pulled.

### 4. Configure
```bash
cp .env.example .env   # then edit .env if you want Telegram alerts / a non-default DB
```

### 5. Run the web app
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

## 📱 Price Watcher — a second, always-on app

`price_watcher.py` is a separate, standalone daemon from the Flask search UI — it doesn't need the web app running at all. Point it at a short, hand-picked list of specific flights and it checks each one every few minutes, forever, sending a Telegram message straight to your phone the moment a price changes (up or down).

### Setup
```bash
cd app
cp watchlist.example.json watchlist.json   # then edit it — see format below
```
Watchlist format — a plain JSON array, one entry per flight you want watched:
```json
[
  {"origin": "KRK", "destination": "BCN", "date": "2026-09-15", "label": "Wakacje w Barcelonie"},
  {"origin": "KTW", "destination": "OSL", "date": "2026-10-01"},
  {"origin": "KRK", "destination": "RHO", "date": "2026-09-17", "airline": "Ryanair"}
]
```
`label` is optional (defaults to `ORIGIN → DESTINATION`). `watchlist.json` is gitignored — it's your own picks, not committed.

`airline` is also optional. Without it, a check tracks *whatever's cheapest overall* — any carrier, any number of stops, same as the web UI's search. With it, the watcher scans the full results list (not just the top card) for that airline's own price specifically, and — unless you add `"direct_only": false` to the entry — only counts a flight with no connections. This matters concretely: for one real route checked while building this, the "cheapest overall" fare was a connecting itinerary on a different airline entirely, undercutting the budget carrier's own direct flight further down the list — exactly the case `airline` + `direct_only` exists to avoid.

Also set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in `.env` (see Configuration above) — without them, price changes are only logged to the console, not sent to your phone.

### Run it
```bash
# foreground, for testing:
cd app && ../venv/bin/python price_watcher.py

# as a real background service (macOS, starts on login, restarts on crash):
scripts/install_price_watcher_service.sh
# stop/remove it later:
scripts/uninstall_price_watcher_service.sh
```
Logs land in `~/Library/Logs/cheap-flights-price-watcher/` when run as a service.

### Configuration (`.env`)
- `WATCHER_INTERVAL_SECONDS` — how often to re-check every watched flight (default `180` = 3 min).
- `WATCHER_JITTER_SECONDS` — random +/- seconds around that interval (default `20`), so the schedule isn't perfectly periodic.

### Running it on GitHub Actions instead (survives your Mac being off)

The LaunchAgent above only runs while your Mac is on, awake, and you're logged in. `.github/workflows/price_watcher.yml` runs the watcher from GitHub's own infrastructure instead — genuinely always-on, independent of your machine — trading the exact 3-minute cadence for one GitHub can actually deliver.

**Why not just point GitHub Actions at `WATCHER_INTERVAL_SECONDS=180`**: it can't. GitHub Actions enforces a hard 5-minute floor on `schedule` cron triggers, and even that isn't guaranteed — scheduled runs are commonly delayed 5-30+ minutes during high load, especially right at :00/:30 past the hour. There is no way to get real 3-minute checks out of it. The workflow here uses `python price_watcher.py --once` (a single check-and-exit, not the looping mode) on a 15-minute schedule, offset from the busy times.

It also can't reach your local Postgres — GitHub's runners have no route to `localhost` on your Mac. So `--once` uses a small JSON file (`app/price_history.json`) instead of Postgres for "last seen price", and the workflow commits that file back to the repo after every run so the history persists between runs. **Its keys are a hash of origin+destination+date, not the plaintext route** — this repo is public, so a plaintext key would publish your actual travel dates in the commit history forever, even if later "deleted" (public history can be cached/forked). Hashing means the committed file doesn't read as a legible itinerary.

**Setup** (GitHub web UI, Settings → Secrets and variables → Actions → New repository secret):
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — same values as your `.env`.
- `WATCHLIST_JSON` — the full contents of your `app/watchlist.json`, pasted as one secret. It's written to `watchlist.json` fresh at the start of every run and never committed — same privacy reasoning as the hashed history file, just for the input side instead of the output side.

Then either wait for the schedule, or trigger a run immediately from the repo's **Actions** tab → "Price Watcher" → **Run workflow**.

**Running both at once**: nothing stops you from running the local LaunchAgent *and* the GitHub Actions workflow simultaneously — they use separate state (Postgres vs. `price_history.json`) and won't conflict, though you may get a notification from each shortly after the same real price change.

### ⚠️ Read before setting this up
- **This is a materially different traffic pattern than the search UI**: the same exact query, on a fixed schedule, forever — a much more bot-like signature than one-off searches, and a real risk of Google eventually blocking the IP it runs from. There's no evasion trick here, just the jitter above. Raising `WATCHER_INTERVAL_SECONDS` is always safe; lowering it below a few minutes trades responsiveness for risk.
- **A LaunchAgent isn't true 24/7**: it only runs while you're logged in and the Mac isn't asleep. For genuine round-the-clock coverage, either stop the Mac from sleeping (Ustawienia > Bateria/Energia) or eventually move this one script to a small always-on server/VPS — nothing about it depends on the rest of this repo running anywhere in particular.
- "Price changed" means *any* change, up or down — there's no threshold/direction filter yet.

---

## 📂 Project Structure
```
Cheap-Flights-App/
│
├── .github/workflows/
│   └── price_watcher.yml       # runs price_watcher.py --once on a schedule (see "Price Watcher")
├── app/
│   ├── webapp.py               # Flask app: search form + results
│   ├── templates/index.html    # the search page
│   ├── core/
│   │   ├── googleflights.py    # Playwright scraper for one Google Flights leg
│   │   ├── search.py           # scans routes/dates, pairs legs into round-trip offers
│   │   ├── travel_intent.py    # local Ollama: free-text query -> destination airport codes
│   │   ├── date_intent.py      # local Ollama + plain Python: free-text query -> concrete dates
│   │   ├── ollama_client.py    # shared HTTP call to the local Ollama model (JSON-schema constrained)
│   │   ├── weather.py          # lookup into precomputed climate_normals.json
│   │   ├── airports.py         # server-side loader for static/airports.json
│   │   ├── telegram.py         # Telegram sender
│   │   └── utils.py            # generate_dates() helper
│   ├── static/
│   │   ├── airports.json       # curated airport list (code, country, region, lat/lon, ...)
│   │   └── climate_normals.json # precomputed avg monthly temp per airport (see scripts/)
│   ├── database.py             # Postgres persistence (init_db / save_flight_result)
│   ├── price_watcher.py        # second, standalone app: 24/7 price-change alerts to Telegram
│   ├── watchlist.example.json  # copy to watchlist.json (gitignored) and add your own flights
│   └── price_history.json      # --once mode's state (hashed keys) — committed by the GH Actions workflow
│
├── scripts/
│   ├── fetch_climate_normals.py # one-time/occasional: (re)build climate_normals.json from Open-Meteo
│   ├── install_price_watcher_service.sh   # installs price_watcher.py as a macOS LaunchAgent
│   └── uninstall_price_watcher_service.sh
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
- `airline`-filtered watchlist checks (`search_flight_google_for_airline`) only look through the results Google has actually rendered on the page — they don't scroll or force-load more. If your airline's flight isn't among the first batch of results for a route, the check reports "no result" (logged, not silently treated as a price of zero/unavailable) rather than finding it further down.
- A search runs synchronously in the request — the page waits for the whole scrape before showing results, with no progress indicator beyond a spinner. Legs are now scraped concurrently (`SCRAPE_CONCURRENCY`, default 5 at once) and a leg already scraped within `CACHE_MAX_AGE_MINUTES` is reused from Postgres instead of re-scraped, which cuts a lot of the wait for wide searches and for repeat/overlapping ones — but a wide first-time search (many airports/dates, or "🌍 Dokądkolwiek" against all 161 curated airports) can still take a while. Narrow the date range for wide searches.
- Raising `SCRAPE_CONCURRENCY` too high risks Google rate-limiting or bot-detecting the scraper sooner than the current sequential-ish pace does — there's no backoff/retry on that yet, a blocked leg just comes back as "no results found" like any other scrape failure.
- AI destination/date search needs Ollama running locally with `OLLAMA_MODEL` pulled — an empty query ("anywhere" / exact date pickers) needs neither and makes no model call at all.
- A "weekend" search scans every Thu/Fri/Sat departure against every Sat/Sun/Mon return across the whole named month, which is a lot more origin×destination×date combinations than a narrow exact-date search (e.g. 21 destinations × 12 candidate departure days × 2 directions = 500+ legs for one origin, one country, one month) — expect it to take a while even with concurrent scraping and the cache. Narrowing to fewer destinations (a more specific "Dokąd?" query) speeds this up more than anything else.
- The local model (llama3.1:8b) is measurably unreliable on its own for this task: testing turned up both hallucinated countries for places outside this app's network (asked for "Japonia", got back "Italy" instead of "not covered") and invented temperature numbers on queries that never mentioned weather at all (apparently parroted straight from this file's own prompt examples). Every country and temperature the model returns is therefore re-verified against the literal query text in `core/travel_intent.py` before being trusted — a country has to actually be named (or its Polish translation) in the query, and a temperature is only kept if the query mentions weather/temperature at all. This is a real safety net, not a formality: it's what makes the "unsupported place" case report "no matches" instead of a wrong destination. The cost is that genuinely creative geographic expansion (e.g. "southern Europe" meaning several unnamed countries) is less reliable than a hosted frontier model would be, since the safety net can only verify what's actually written in the query.
- Weather filtering ("somewhere over 20°C") checks a *historical monthly average* (from `climate_normals.json`, 2020–2025), not a real forecast — it tells you what a month is normally like at that airport, not what it'll actually be on your specific dates. Re-run `scripts/fetch_climate_normals.py` occasionally to keep the average current.
- There's no automated test suite yet.

---

## 📜 License
MIT License
