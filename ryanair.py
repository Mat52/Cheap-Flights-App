from playwright.sync_api import sync_playwright
from datetime import datetime
import re
from config import AIRPORT_NAME_HINT, ORIGINS, DESTINATIONS, DATESDEPARTURE, DATESBACK, PRICE_THRESHOLD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MONTH_MAP
import requests
def search_flight(origin, destination, date_out):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=30)
        context = browser.new_context()
        page = context.new_page()
        print(PRICE_THRESHOLD)
        try:
            print(f"🔍 Sprawdzam: {origin} -> {destination} ({date_out})")
            page.goto("https://www.ryanair.com/pl/pl")

            try:
                page.wait_for_selector("button[data-ref='cookie.accept-all']", timeout=1000)
                page.click("button[data-ref='cookie.accept-all']")
                print("🍪 Zaakceptowano cookies")
            except:
                print("ℹ️ Brak popupu cookies")

            try:
                page.wait_for_selector("label[for='ry-radio-button--0']", timeout=1000)
                page.click("label[for='ry-radio-button--0']")
                print("✈️ Wybrano lot w jedną stronę")
            except:
                print("⚠️ Nie udało się kliknąć 'W jedną stronę'")

            page.wait_for_selector("#input-button__departure", timeout=5000)
            page.click("#input-button__departure")
            page.fill("#input-button__departure", "")
            page.keyboard.type(AIRPORT_NAME_HINT[origin][:3])
            page.wait_for_selector(f"span[data-ref='airport-item__name'][data-id='{origin}']", timeout=1000)
            page.click(f"span[data-ref='airport-item__name'][data-id='{origin}']")

            page.wait_for_selector("#input-button__destination", timeout=5000)
            page.click("#input-button__destination")
            page.fill("#input-button__destination", "")
            page.keyboard.type(AIRPORT_NAME_HINT[destination][:3])
            try:
                page.wait_for_selector(f"span[data-ref='airport-item__name'][data-id='{destination}']", timeout=1000)
                page.click(f"span[data-ref='airport-item__name'][data-id='{destination}']")
            except:
                print(f"❌ Lotnisko docelowe {destination} niedostępne lub brak połączenia, przerywam")
                return None

            dt = datetime.strptime(date_out, "%Y-%m-%d")
            month_str = MONTH_MAP[dt.strftime("%m")]
            page.wait_for_selector(f"div.m-toggle__month[data-ref='m-toggle-months-item'][data-id='{month_str}']", timeout=1000)
            page.click(f"div.m-toggle__month[data-ref='m-toggle-months-item'][data-id='{month_str}']")

            print("🔍 Szukam dostępnych dni w kalendarzu:")
            calendar_days = page.query_selector_all("div.calendar-body__cell[data-id]")
            day_found = False
            for day in calendar_days:
                date_id = day.get_attribute("data-id")
                classes = day.get_attribute("class")
                if date_id == date_out:
                    if "calendar-body__cell--disabled" in classes:
                        print(f"⛔ Data {date_out} jest niedostępna (disabled), przerywam")
                        return None
                    else:
                        day_found = True

            if not day_found:
                print(f"❌ Data {date_out} niedostępna w kalendarzu, przerywam")
                return None

            day_selector = f"div.calendar-body__cell[data-id='{date_out}']"
            page.wait_for_selector(day_selector, timeout=1000, state="visible")
            page.locator(day_selector).scroll_into_view_if_needed()
            page.click(day_selector)
            print(f"📅 Wybrano datę: {date_out}")

            page.click("[data-ref='flight-search-widget__cta']")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            price_elements = page.query_selector_all("flights-price-simple.flight-card-summary__full-price")
            prices = []
            for el in price_elements:
                try:
                        print(el.inner_text())
                        if (el.inner_text().endswith("€")):
                            price_text = el.inner_text().replace("€", "").strip()
                            response = requests.get("http://api.nbp.pl/api/exchangerates/rates/A/EUR?format=json")
                            data = response.json()
                            kurs = data["rates"][0]["mid"]
                            price = float(price_text.replace(",", ".")) * kurs
                            price_rounded = round(price, 2)
                            prices.append(price_rounded)
                            print(prices[0])
                        if (el.inner_text().endswith("MAD")):
                            print("siema")
                            price_text = el.inner_text().replace("MAD", "").strip()
                            kurs = 0.40
                            price_text = re.sub(r"\s+", "", price_text)
                            print(price_text)
                            price = float(price_text.replace(",", ".")) * kurs
                            price_rounded = round(price, 2)
                            prices.append(price_rounded)
                        if (el.inner_text().endswith("zł")):
                            price_text = el.inner_text().replace("zł", "").strip()
                            price = float(price_text.replace(",", "."))
                            price_rounded = round(price, 2)
                            prices.append(price_rounded)
                            print(prices[0])
                        
                        
                except:
                    continue

            if not prices:

                return None

            min_price = min(prices)

            return {
                "origin": origin,
                "destination": destination,
                "date": date_out,
                "price": min_price,
                "Airline": "Ryanair"
            }

        except Exception as e:
            print(f"❌ Błąd scrapera: {e}")
            return None
        finally:
            browser.close()



