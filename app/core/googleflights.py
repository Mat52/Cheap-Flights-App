from playwright.sync_api import sync_playwright
from datetime import datetime
import re
import requests
def search_flight_google(page, origin, destination, date_out, cookies):
        try:
            url = f"https://www.google.com/travel/flights?hl=pl&q=flights+from+{origin}+to+{destination}+on+{date_out}+oneway"
            print(f"🌐 Otwieram: {url}")
            page.goto(url)

            if(cookies == True):
                try:
                    page.wait_for_selector("button:has-text('Zaakceptuj wszystko')", timeout=1000) #tutaj timeout
                    page.click("button:has-text('Zaakceptuj wszystko')", timeout=1000) #tutaj timeout
                    print("✅ Zaakceptowano cookies")
                except:
                    print("ℹ️ Brak popupu cookies")
            page.wait_for_selector("div[role='tab']", timeout=1500)
            page.locator("div[role='tab']").filter(has_text="Najtaniej").click(timeout=1000)

            page.wait_for_selector("span[aria-label*='złotych'], span[aria-label*='złote']", timeout=2000)
            price = page.locator("span[aria-label*='złotych'], span[aria-label*='złote']").first.text_content()
            price_text = price.replace("zł", "").strip()

            price = price_text
            print(price_text)
            price = re.sub(r"\s+", "", price)
            price = float(price)
            print(price)
            flight_box = page.locator("div.sSHqwe.tPgKwe.ogfYpf").first
            all_spans = flight_box.locator("span")

            airline = None
            for i in range(all_spans.count()):
                text = all_spans.nth(i).text_content().strip()
                if text and not text.startswith("Obsługiwany"):
                    airline = text
                    break
            print(airline)
            try:
                locator = page.locator("span[aria-label^='Godzina przylotu']").first
                locator.wait_for(state="attached", timeout=500)  # 10 sekund (w milisekundach)
                arrival_time = locator.text_content()
            except:
                print("⏭️ Pomijam brakujący element: Godzina przylotu ")
                arrival_time = "brak danych"
            try:
                locator = page.locator("span[aria-label^='Godzina wylotu']").first
                locator.wait_for(state="attached", timeout=500)  # czekaj max 10 sek
                departure_time = locator.text_content()
            except:
                print("⏭️ Pomijam brakujący element: Godzina wylotu ")
                departure_time = "brak danych"

            return {
                "origin": origin,
                "destination": destination,
                "date": date_out,
                "price": price,
                "Airline": airline,
                "departure": departure_time,
                "arrival":arrival_time,

            }








            
            



        except Exception as e:
            print(f"❌ Błąd scrapera: {e}")
            return None
        finally: 
            print("done")



