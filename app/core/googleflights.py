from playwright.async_api import Page
import re


async def search_flight_google(page: Page, origin, destination, date_out):
    try:
        url = f"https://www.google.com/travel/flights?hl=pl&q=flights+from+{origin}+to+{destination}+on+{date_out}+oneway"
        print(f"🌐 Otwieram: {url}")
        await page.goto(url, timeout=15000)

        # Defensive on every page, not just the first: Google's consent
        # cookie lives in the browser context, so once any page in this
        # context has accepted it the dialog won't reappear for the rest —
        # but concurrent pages racing on their very first navigation may
        # each still see it once, so every page tries independently.
        try:
            await page.wait_for_selector("button:has-text('Zaakceptuj wszystko')", timeout=1000)
            await page.click("button:has-text('Zaakceptuj wszystko')", timeout=1000)
            print("✅ Zaakceptowano cookies")
        except Exception:
            print("ℹ️ Brak popupu cookies")

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
