# Flight data API research — replacing/supplementing the Google Flights scraper

Goal: find a free-or-cheap API that can replace or supplement the current
Playwright/Google-Flights scraper, specifically for **low-cost carriers**
(Ryanair, Wizz Air, easyJet), which is what this app actually cares about.

## TL;DR / recommendation

There is no free, official, self-serve API that gives clean structured
pricing for Ryanair + Wizz Air + easyJet together. LCCs deliberately avoid
third-party distribution (GDS/OTA fees eat their margin), so every
"aggregator" API either excludes them, requires a partner application, or
costs money per call/booking. Concretely:

1. **Keep the current Google Flights scrape as the primary source** — it
   already carries real Ryanair and Wizz Air fares (confirmed below), it's
   free, and it needs no API key. The actual problem with it is speed and
   fragility, not LCC coverage — that's a scraper-performance fix (see the
   earlier discussion: parallelize the Playwright contexts), not an API swap.
2. **If we still want a second source, evaluate Duffel** for easyJet
   specifically (officially supported, well-documented, cheap: free to
   search up to a search/book ratio, then $0.005/search). Don't expect
   Ryanair there.
3. **Do not re-attempt direct Ryanair/Wizz Air site scraping** — this repo
   already tried that (see "What we tried before" below) and hit anti-bot
   walls hard enough to abandon it for Google Flights. The *unofficial JSON
   endpoints* (not UI scraping) are a genuinely different, lighter-weight
   option than what was tried before, but they're undocumented, ToS-risky,
   and break without notice — treat as a "nice to have, low trust" fallback
   at most, not the backbone of the app.
4. **Kiwi Tequila and Amadeus are dead ends** for this use case specifically
   — see why below.

## What we tried before (this repo's own history)

`git show 35c9b8a` (initial commit) still has the deleted `ryanair.py` and
`wizzair.py`. Both did full **Playwright UI automation directly against
ryanair.com / wizzair.com** (clicking date pickers, typing into autocomplete
fields), not their JSON APIs. The Wizz Air version in particular used
`launch_persistent_context`, `--disable-blink-features=AutomationControlled`,
webdriver-property spoofing, and a hardcoded `input("click something
manually...")` pause — i.e. it needed active anti-bot evasion and manual
babysitting to get past their bot detection. That's almost certainly why the
project moved to scraping Google Flights instead: one scraper, one
(comparatively) bot-tolerant target, instead of three adversarial ones.

## Option-by-option

### Kiwi.com Tequila API
- **Coverage**: the best of any aggregator — 800+ airlines including LCCs,
  purpose-built for exactly this ("cheapest anywhere" style search).
- **Access**: self-serve signup was closed in May 2024. In 2026 it's
  partner-application-only via `tequila.kiwi.com/portal` — Kiwi decides if
  your use case qualifies, this is a business relationship, not a signup
  form. Not realistic for a personal project.
- **Cost**: free registration for approved partners, revenue-share on actual
  bookings — irrelevant since we can't get in without a business case.
- **Verdict**: best data, unreachable for us. Skip.

### Amadeus Self-Service APIs
- **Coverage**: Amadeus overall (Enterprise tier) covers 400+ airlines
  including Ryanair via their Navitaire PSS relationship — but that's
  Enterprise, not what we'd sign up for.
- **The catch**: the free **Self-Service** tier explicitly **excludes
  low-cost-carrier content** (and excludes AA/Delta/BA too). To get
  Ryanair/Wizz Air out of Amadeus you need the paid Enterprise suite with
  NDC access — a real B2B sales process, not an API key from a dev portal.
- **Verdict**: the free tier that's actually easy to sign up for is useless
  for this app's whole point (cheap LCC fares). Skip.

### Skyscanner
- **Official Travel API**: partner-only, case-by-case approval, "not an
  established travel business" applications aren't guaranteed approval.
  Not realistic for a personal project.
- **Unofficial alternative**: "Sky Scrapper" on RapidAPI — a third party's
  wrapper around Skyscanner's own site, with a free tier and no partner
  agreement. This trades "we scrape Google" for "someone else scrapes
  Skyscanner and we depend on their free-tier limits and uptime" — not
  obviously better than what we already run ourselves, and less control.
- **Verdict**: official path closed; unofficial path is a lateral move at
  best. Skip unless we specifically want Skyscanner's route-finder features.

### Duffel
- **Coverage**: 300+ airlines. **easyJet is officially, explicitly
  supported** (Duffel has a dedicated easyJet integration page). Wizz Air
  shows up in some of Duffel's own low-cost-carrier marketing copy, but
  that's not the same as a confirmed, current API coverage entry — needs
  verification against their live airline list before relying on it.
  **Ryanair was not confirmed anywhere** in this research; Ryanair is
  broadly known for refusing GDS/NDC/OTA distribution deals to protect
  direct-booking margins, so its absence from Duffel would be consistent
  with that pattern, not a fluke.
- **Access**: real self-serve developer signup, good docs, a free sandbox
  ("Duffel Airways" test airline — note: sandbox data is synthetic, not real
  schedules/prices, so it's only useful for wiring up the integration, not
  for actually finding cheap flights).
- **Cost**: $3 per confirmed order, 1% of order value for managed content,
  $1 per paid ancillary, and a search fee of $0.005 per search once you
  exceed a 1,500-searches-per-booking ratio. Since this app searches
  constantly but would rarely/never place a real "order," expect to land in
  the $0.005/search tier fairly quickly — still cheap (thousands of searches
  ≈ single-digit dollars) but **not literally free** at any real usage
  volume, and it's a metered cost with no cap unless we self-limit.
- **Verdict**: the one option here with an honest, self-serve signup and
  real docs. Worth trying **only for easyJet** if that route matters enough
  to justify a metered cost; don't expect Ryanair.

### Unofficial per-airline JSON endpoints (Ryanair, Wizz Air)
- **Ryanair**: `/api/booking/v4/*/availability` — the same endpoint
  ryanair.com's own frontend calls. There's an actively-maintained
  open-source client (`2BAD/ryanair` on GitHub, TypeScript) that hits it
  directly with plain HTTP + a couple of required headers/cookies (a
  `fr-correlation-id` and a `client-version` that has to match the
  currently-deployed web build — the client scrapes that version and
  auto-updates when Ryanair's site redeploys and the old pin gets a 409).
  This is genuinely lighter than a browser: it's a JSON GET/POST, no
  Playwright needed, so it'd be *much* faster than either the old UI-scraper
  or the current Google Flights approach.
- **Wizz Air**: similarly has an undocumented JSON endpoint
  (`https://be.wizzair.com/<version>/Api/search/timetable`), used by several
  GitHub scrapers — but multiple of those repos note Wizz Air "changes its
  API version frequently" and needs manual updates, and one Apify scraper
  for it is marked **deprecated**. Less stable than the Ryanair one.
- **easyJet**: no comparable public unofficial JSON endpoint turned up in
  this research — easyJet appears to be less commonly reverse-engineered
  than the other two, likely why Duffel's official route is the more
  realistic option for it.
- **Risk, for both**: undocumented and unversioned — can change or start
  blocking at any time with no notice, and Ryanair specifically has a
  history of suing scrapers/OTAs over unauthorized fare use (e.g. the
  Ryanair v. Booking.com litigation), even though these "fare finder"
  endpoints don't require login or payment bypass. This is a materially
  different risk profile than reading Google's own public flight-search
  page, and it's also exactly the category of adversarial target that made
  the previous UI-scraping attempt in this repo get abandoned. Given that
  history, this should be a low-trust, easily-disabled fallback, not a
  primary dependency.

### Travelpayouts (Aviasales) Data API
- **Coverage**: cached/aggregated fare data across many sources, including
  LCCs, via Aviasales' metasearch — but it's positioned for trend data
  ("best time to fly", cheapest month) built from historical/cached prices,
  not a live per-date shopping call. Free to register, monetized via
  affiliate commission rather than per-call fees.
- **Verdict**: could be a decent *supplementary* signal (e.g. "is this route
  usually this cheap?") but isn't a live-price replacement for the current
  scraper. Low priority.

### Google Flights (current approach) — for comparison
- **Coverage confirmed**: Ryanair fares do appear on Google Flights, each
  with a dedicated Ryanair booking page (this reversed a long-standing
  historical dispute where Ryanair kept itself off metasearch engines).
  Wizz Air is also listed among the ultra-low-cost carriers Google Flights
  indexes. So the current scraper's target genuinely does carry the fares
  this app is trying to find — the known issues are scraper speed/fragility
  (documented already in the README), not missing LCC data.
- **Caveat worth keeping in mind**: budget-carrier prices on Google Flights
  can show a base fare before bag/seat add-ons that get tacked on at the
  airline's own checkout — the same caveat applies to whatever API we might
  add, since none of them are the airline's own real-time bundled price
  either.

## Comparison table

| Option | Ryanair | Wizz Air | easyJet | Self-serve signup? | Cost | Data freshness |
|---|---|---|---|---|---|---|
| Google Flights (current scraper) | ✅ confirmed | ✅ confirmed | ✅ (major EU carrier, listed) | n/a (scraping) | free | live |
| Kiwi Tequila | ✅ (best-in-class) | ✅ | ✅ | ❌ partner-approval only | free if approved | live |
| Amadeus Self-Service | ❌ excluded from free tier | ❌ excluded | ❌ excluded | ✅ but useless here | free (but no LCC data) | n/a |
| Skyscanner official | unknown, likely yes | unknown, likely yes | unknown, likely yes | ❌ partner-approval only | unknown | n/a (can't get in) |
| Duffel | ❌ not found | ⚠️ unconfirmed, marketed as covered | ✅ confirmed | ✅ real self-serve | metered, cheap ($0.005/search after ratio, $3/order) | live |
| Unofficial Ryanair JSON endpoint | ✅ (it's their own live data) | n/a | n/a | ✅ (no key, undocumented) | free | live, but fragile/ToS risk |
| Unofficial Wizz Air JSON endpoint | n/a | ✅ (their own live data) | n/a | ✅ (no key, undocumented) | free | live, but breaks often |
| Travelpayouts Data API | ✅ (aggregated) | ✅ (aggregated) | ✅ (aggregated) | ✅ | free (affiliate model) | cached/trend, not live shopping |

## Suggested next step

Given the above, the highest-value next step isn't actually an API swap —
it's making the existing Google Flights scraper faster and more resilient
(bounded-concurrency Playwright contexts, as discussed separately), since it
already has confirmed real coverage of all three target carriers for free.
An unofficial Ryanair JSON client (`2BAD/ryanair`-style) could be prototyped
as a *free, fast, optional second source* behind a feature flag — with the
understanding that it can stop working at any time and shouldn't be
something a Telegram price alert depends on exclusively.
