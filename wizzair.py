from playwright.sync_api import sync_playwright
from datetime import datetime
import re
from config import AIRPORT_NAME_HINT, ORIGINS, DESTINATIONS, DATESDEPARTURE, DATESBACK, PRICE_THRESHOLD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MONTH_MAP
import requests
from mapyearforwizz import ReturnMonthAndYear
from playwright.sync_api import sync_playwright

def search_wizzair_flight(origin, destination, date_out):
    with sync_playwright() as p:
    # 1. Tworzymy persistent profile – jak prawdziwa przeglądarka z historią
        context = p.chromium.launch_persistent_context(
            user_data_dir="/tmp/wizzair-profile-1",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process"
            ],
            viewport={"width": 1280, "height": 800},
            locale="pl-PL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # 2. Pobieramy pierwszą stronę lub tworzymy nową
        page = context.pages[0] if context.pages else context.new_page()

        # 3. Ukrywamy "webdriver" (anty-bot)
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # 4. Odwiedzamy stronę
        page.goto("https://www.wizzair.com/pl-pl")
        page.wait_for_timeout(5000)  # czekamy na pełne załadowanie

        input("🛑 Kliknij coś ręcznie, potem naciśnij Enter, by kontynuować…")
        try:
            print(f"🔍 Sprawdzam: {origin} -> {destination} ({date_out})")

            try:
                page.wait_for_selector("button#onetrust-accept-btn-handler", timeout=5000)
                page.click("button#onetrust-accept-btn-handler")
                print("🍪 Zaakceptowano cookies")
            except:
                print("ℹ️ Brak popupu cookies")
            try:
                page.wait_for_selector("input[data-test='oneway']", timeout=5000)
                page.click("input[data-test='oneway']")
                print("✈️ Wybrano lot w jedną stronę")
            except:
                print("⚠️ Nie udało się kliknąć 'W jedną stronę'")

            page.wait_for_selector("input[data-test='search-departure-station']", timeout=5000)
            page.click("input[data-test='search-departure-station']")
            page.fill("input[data-test='search-departure-station']", "")
            page.keyboard.type(AIRPORT_NAME_HINT[origin][:3])
            label_selector = f"label:has(small:has-text('{origin}'))"
            page.wait_for_selector(label_selector, timeout=1000)
            page.click(label_selector)

            page.keyboard.type(AIRPORT_NAME_HINT[destination][:3])
            try:
                label_selector = f"label:has(small:has-text('{destination}'))"
                print(label_selector)
                page.wait_for_selector(label_selector, timeout=3000)
                page.click(label_selector)
            except:
                print(f"❌ Lotnisko docelowe {destination} niedostępne lub brak połączenia, przerywam")
                return None

            selector = f"div.vc-title:has-text('{ReturnMonthAndYear()}')"
            page.wait_for_selector(selector, timeout=2000)
            page.click(selector)

            dt = datetime.strptime(date_out, "%Y-%m-%d")
            year = dt.strftime("%Y")

            element = page.query_selector("span.vc-nav-title")
            visible_year = element.inner_text().strip()

            if (year == str(visible_year)):
                month_str = MONTH_MAP[dt.strftime("%m")]
                selector = f"span.vc-nav-item:has-text('{month_str}')"
                page.wait_for_selector(selector, timeout=3000)
                page.click(selector)


                xpath = f"//div[contains(@class, 'id-{date_out}')]//span[@class='vc-day-content vc-focusable']"

                page.wait_for_selector(f"xpath={xpath}", timeout=3000)
                element = page.query_selector(f"xpath={xpath}")

                if element:
                    aria_disabled = element.get_attribute("aria-disabled")
                    if aria_disabled == "true":
                        print(f"🚫 Dzień {date_out} jest niedostępny. Kończę scrapowanie.")
                        return  # lub raise Exception(), exit(), break, etc.
                    else:
                        print(f"✅ Dzień {date_out} jest aktywny. Klikam.")
                        element.click()
                else:
                    print(f"❌ Nie znaleziono elementu dla dnia {date_out}")







            else:
                print("nie ten rok")
            



            

            

 

       
        except Exception as e:
            print(f"❌ Błąd scrapera: {e}")
            return None
        finally:
            input("⏸️ Naciśnij Enter przed zamknięciem przeglądarki...")
            browser.close()

