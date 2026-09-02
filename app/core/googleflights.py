from playwright.async_api import BrowserContext, Page
import re


async def warm_up_cookies(context: BrowserContext):
    """Accept Google's cookie-consent dialog once, sequentially, on a
    scratch page, before any concurrent scraping starts.

    This isn't defensive polish — measured directly: without it, raising
    scrape concurrency past ~5 made almost every leg fail (29/30 at
    concurrency 15), all logging "waiting for consent.google.com/save
    navigation to finish". Every page in a shared BrowserContext hitting
    Google Flights for the first time races on that same consent-redirect
    dance at once, and it falls apart. Doing it once, sequentially, before
    any concurrent page exists means the consent cookie is already sitting
    in the context's cookie jar by the time they navigate, so none of them
    ever see the dialog or the redirect at all.
    """
    page = await context.new_page()
    try:
        await page.goto("https://www.google.com/travel/flights?hl=pl", timeout=15000)
        try:
            await page.wait_for_selector("button:has-text('Zaakceptuj wszystko')", timeout=5000)
            await page.click("button:has-text('Zaakceptuj wszystko')", timeout=2000)
            print("✅ Zaakceptowano cookies (warm-up)")
        except Exception:
            print("ℹ️ Brak popupu cookies (warm-up)")
    finally:
        await page.close()


async def search_flight_google(page: Page, origin, destination, date_out):
    try:
        url = f"https://www.google.com/travel/flights?hl=pl&q=flights+from+{origin}+to+{destination}+on+{date_out}+oneway"
        print(f"🌐 Otwieram: {url}")
        await page.goto(url, timeout=15000)

        # warm_up_cookies() already accepted this once, sequentially, before
        # any concurrent page existed — this is just a cheap fallback in
        # case consent state was somehow lost mid-search. Short timeout on
        # purpose: at concurrency, this runs on every leg, and the button
        # normally isn't there to find.
        try:
            await page.wait_for_selector("button:has-text('Zaakceptuj wszystko')", timeout=300)
            await page.click("button:has-text('Zaakceptuj wszystko')", timeout=1000)
            print("✅ Zaakceptowano cookies")
        except Exception:
            pass

        await page.wait_for_selector("div[role='tab']", timeout=1500)
        await page.locator("div[role='tab']").filter(has_text="Najtaniej").click(timeout=1000)

        await page.wait_for_selector("span[aria-label*='złotych'], span[aria-label*='złote']", timeout=2000)
        price_text = await page.locator("span[aria-label*='złotych'], span[aria-label*='złote']").first.text_content()
        price_text = price_text.replace("zł", "").strip()

        price = re.sub(r"\s+", "", price_text)
        price = float(price)
        print(price)

        flight_box = page.locator("div.sSHqwe.tPgKwe.ogfYpf").first
        all_spans = flight_box.locator("span")

        airline = None
        span_count = await all_spans.count()
        for i in range(span_count):
            text = (await all_spans.nth(i).text_content()).strip()
            if text and not text.startswith("Obsługiwany"):
                airline = text
                break
        print(airline)

        try:
            locator = page.locator("span[aria-label^='Godzina przylotu']").first
            await locator.wait_for(state="attached", timeout=500)
            arrival_time = await locator.text_content()
        except Exception:
            print("⏭️ Pomijam brakujący element: Godzina przylotu ")
            arrival_time = "brak danych"
        try:
            locator = page.locator("span[aria-label^='Godzina wylotu']").first
            await locator.wait_for(state="attached", timeout=500)
            departure_time = await locator.text_content()
        except Exception:
            print("⏭️ Pomijam brakujący element: Godzina wylotu ")
            departure_time = "brak danych"

        return {
            "origin": origin,
            "destination": destination,
            "date": date_out,
            "price": price,
            "Airline": airline,
            "departure": departure_time,
            "arrival": arrival_time,
        }

    except Exception as e:
        print(f"❌ Błąd scrapera ({origin} -> {destination}, {date_out}): {e}")
        return None


async def search_flight_google_for_airline(page: Page, origin, destination, date_out, airline, direct_only=True):
    """Like search_flight_google, but for "I specifically want <airline>'s
    price on this route" rather than "whatever's cheapest overall."

    The base scraper only ever reads the single cheapest card on the
    "Najtaniej" tab — for a route where a connecting itinerary on a
    different carrier undercuts it (seen live: RHO->KRK showed an
    Edelweiss/SWISS connection via Zurich as cheapest, with Ryanair's own
    direct flight further down the list, not hidden), that's the wrong
    price for someone tracking a specific airline. This scans every
    result row instead of just the first, in page order (already
    price-ascending on this tab), and returns the first one whose airline
    text contains `airline` (case-insensitive) — and, by default, that has
    no connections, since a budget-carrier watch is almost always about
    that carrier's own direct service, not a codeshare/connection through
    someone else's hub. Returns None if nothing matches among the results
    Google actually rendered (this doesn't force-load more).
    """
    try:
        url = f"https://www.google.com/travel/flights?hl=pl&q=flights+from+{origin}+to+{destination}+on+{date_out}+oneway"
        print(f"🌐 Otwieram: {url}")
        await page.goto(url, timeout=15000)

        try:
            await page.wait_for_selector("button:has-text('Zaakceptuj wszystko')", timeout=300)
            await page.click("button:has-text('Zaakceptuj wszystko')", timeout=1000)
        except Exception:
            pass

        await page.wait_for_selector("div[role='tab']", timeout=1500)
        await page.locator("div[role='tab']").filter(has_text="Najtaniej").click(timeout=1000)
        # A fixed wait here isn't enough on its own — measured directly: a
        # 2.5s flat wait before reading the list left prices still
        # unrendered often enough to make an existing flight's own
        # <li> come back with no "zł" in it at all. Wait for a concrete
        # signal instead (some price has actually rendered), then a short
        # buffer for the rest of the list to catch up.
        await page.wait_for_selector("span[aria-label*='złotych'], span[aria-label*='złote']", timeout=5000)
        await page.wait_for_timeout(1200)

        # all_inner_texts() reads every <li>'s text in one batched call —
        # deliberately not a per-index loop over .nth(i).inner_text():
        # measured directly, that racing individual re-queries against a
        # results list that's still reflowing/streaming in caused a real,
        # intermittent Locator.inner_text timeout (a route that worked
        # standalone came back "no result" moments later in a full run).
        # One batched read against a DOM snapshot doesn't have that race.
        row_texts = await page.locator("li").all_inner_texts()
        seen = set()  # short and "expanded detail" <li>s repeat the same flight
        for text in row_texts:
            lowered = text.lower()
            if airline.lower() not in lowered:
                continue
            if direct_only and "bez przesiadek" not in lowered:
                continue

            price_matches = re.findall(r"([\d  ]{2,6})\s*zł", text)
            if not price_matches:
                continue
            price = float(price_matches[-1].replace(" ", "").replace(" ", ""))

            signature = (round(price), lowered[:60])
            if signature in seen:
                continue
            seen.add(signature)

            # The "expanded detail" <li> variant repeats each time token
            # twice back-to-back ("23:1023:10 w dniu ...") — collapse
            # immediate repeats so departure/arrival aren't both the same
            # duplicated departure time.
            raw_times = re.findall(r"\d{1,2}:\d{2}(?:\+\d)?", text)
            times = [t for i, t in enumerate(raw_times) if i == 0 or t != raw_times[i - 1]]
            departure_time = times[0] if times else "brak danych"
            arrival_time = times[1] if len(times) > 1 else "brak danych"

            print(f"{price} ({airline}, direct_only={direct_only})")
            return {
                "origin": origin,
                "destination": destination,
                "date": date_out,
                "price": price,
                "Airline": airline,
                "departure": departure_time,
                "arrival": arrival_time,
            }

        print(f"ℹ️ Brak wyniku dla {airline} ({'bezpośredni' if direct_only else 'dowolny'}) na {origin} -> {destination}, {date_out}")
        return None

    except Exception as e:
        print(f"❌ Błąd scrapera (airline={airline}) ({origin} -> {destination}, {date_out}): {e}")
        return None
