from app.config_sets.config_sylwester import ORIGINS, DESTINATIONS, DATESDEPARTURE, DATESBACK, GRUPY_BAZ, GRUPY_DESTYNACJI
from app.core.googleflights import search_flight_google
from datetime import datetime
from app.config_sets.config_sylwester import PRICE_THRESHOLD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
import requests


def te_same_regiony(a, b, grupy):
    """Sprawdza, czy dwa kody lotnisk należą do tej samej grupy."""
    return any(a in grupa and b in grupa for grupa in grupy)

def znajdz_polaczenia_dwustronne(loty, min_days=3, max_days=6):
    polaczenia = []
    for wylot in loty:
        for powrot in loty:
            if (
                wylot['origin'] != wylot['destination']
                and (wylot['destination'] == powrot['origin'] or te_same_regiony(wylot['destination'], powrot['origin'], GRUPY_DESTYNACJI))
                and (wylot['origin'] == powrot['destination'] or te_same_regiony(wylot['origin'], powrot['destination'], GRUPY_BAZ))
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
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"❌ Błąd wysyłania wiadomości: {e}")

if __name__ == "__main__":
    results = []

    for origin in ORIGINS:
        for country, destinations in DESTINATIONS.items():
            for destination in destinations:
                for date in DATESDEPARTURE:
                    result = search_flight_google(origin, destination, date)
                    if result:
                        results.append(result)
                    else:
                        print(f"ℹ️ Brak wyników: {origin} -> {destination} | {date}")
                    
    for country, destinations in DESTINATIONS.items():
        for destination in destinations:
            for origin in ORIGINS:
                for date in DATESBACK:
                    result = search_flight_google(destination, origin, date)
                    if result:
                        results.append(result)
                    else:
                        print(f"ℹ️ Brak wyników: {destination} -> {origin} | {date}")

    print("\n📋 ZNALEZIONE POŁĄCZENIA:")
    for r in results:
        print(f"✈️ {r['origin']} -> {r['destination']} | {r['date']} | {r['Airline']} |  {r['departure']} | {r['arrival']} | {r['price']} PLN")

    polaczenia = znajdz_polaczenia_dwustronne(results)

    print("\n📋 ZNALEZIONE OKAZJE TAM I Z POWROTEM:")
    wiadomosc = "📋 <b>ZNALEZIONE OKAZJE TAM I Z POWROTEM:</b>\n"
    for p in polaczenia:
        if p['cena'] < PRICE_THRESHOLD:
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
