from core.googleflights import search_flight_google
from datetime import datetime
from playwright.sync_api import sync_playwright
import requests
import os
import importlib
config_module_path = os.getenv("CONFIG_MODULE", "config_sets.config_sylwester")
config = importlib.import_module(config_module_path)

def te_same_regiony(a, b, grupy):
    """Sprawdza, czy dwa kody lotnisk należą do tej samej grupy."""
    return any(a in grupa and b in grupa for grupa in grupy)

def znajdz_polaczenia_dwustronne(loty, min_days=config.MIN_DAYS, max_days=config.MAX_DAYS):
    polaczenia = []
    for wylot in loty:
        for powrot in loty:
            if (
                wylot['origin'] != wylot['destination']
                and (wylot['destination'] == powrot['origin'] or te_same_regiony(wylot['destination'], powrot['origin'], config.GRUPY_DESTYNACJI))
                and (wylot['origin'] == powrot['destination'] or te_same_regiony(wylot['origin'], powrot['destination'], config.GRUPY_BAZ))
                and wylot != powrot
            ):
                try:
                    data_wylotu = datetime.strptime(wylot['date'], "%Y-%m-%d")
                    data_powrotu = datetime.strptime(powrot['date'], "%Y-%m-%d")
                except ValueError:
                    continue
                roznica = (data_powrotu - data_wylotu).days
                if min_days <= roznica <= max_days:
                    polaczenia.append({
                        "tam": wylot,
                        "powrot": powrot,
                        "cena": round(wylot['price'] + powrot['price'], 2),
                        "pobyt": roznica
                    })
    return sorted(polaczenia, key=lambda x: x["cena"])

def wyslij_telegram(msg):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"❌ Błąd wysyłania wiadomości: {e}")

if __name__ == "__main__":

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        results = []
        cookies = True
        for origin in config.ORIGINS:
            for country, destinations in config.DESTINATIONS.items():
                for destination in destinations:
                    for date in config.DATESDEPARTURE:
                        result = search_flight_google(page, origin, destination, date, cookies)
                        if result:
                            results.append(result)
                            cookies = False
                        else:
                            print(f"ℹ️ Brak wyników: {origin} -> {destination} | {date}")
                            cookies = False
                    
        for country, destinations in config.DESTINATIONS.items():
            for destination in destinations:
                for origin in config.ORIGINS:
                    for date in config.DATESBACK:
                        result = search_flight_google(page, destination, origin, date, cookies)
                        if result:
                            results.append(result)
                        else:
                            print(f"ℹ️ Brak wyników: {destination} -> {origin} | {date}")
        browser.close()

    print("\n📋 ZNALEZIONE POŁĄCZENIA:")
    for r in results:
        print(f"✈️ {r['origin']} -> {r['destination']} | {r['date']} | {r['Airline']} |  {r['departure']} | {r['arrival']} | {r['price']} PLN")

    polaczenia = znajdz_polaczenia_dwustronne(results)

    print("\n📋 ZNALEZIONE OKAZJE TAM I Z POWROTEM:")
    wiadomosc = "📋 <b>ZNALEZIONE OKAZJE TAM I Z POWROTEM:</b>\n"
    for p in polaczenia:
        if p['cena'] < config.PRICE_THRESHOLD:
            tam = p['tam']
            powrot = p['powrot']
            tekst = (
                f"\n🛫 {tam['origin']} -> {tam['destination']} | {tam['date']} | {tam['Airline']} | {tam['departure']} | {tam['arrival']} | {tam['price']} PLN"
                f"\n🛬 {powrot['origin']} -> {powrot['destination']} | {powrot['date']} | {powrot['Airline']} | {powrot['departure']} | {powrot['arrival']} | {powrot['price']} PLN"
                f"\n💰 <b>Suma:</b> {p['cena']} PLN | <i>Pobyt:</i> {p['pobyt']} dni\n"
            )
            print(tekst)
            wiadomosc += tekst

    if wiadomosc.strip() != "📋 <b>ZNALEZIONE OKAZJE TAM I Z POWROTEM:</b>":
        wyslij_telegram(wiadomosc)
