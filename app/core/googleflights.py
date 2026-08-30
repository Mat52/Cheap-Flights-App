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
