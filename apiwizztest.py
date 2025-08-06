import requests
from datetime import datetime
from pprint import pprint

# 🔧 Ustawienia — ZMIEŃ na swoje
departure_station = "KRK"   # Kraków
arrival_station = "LTN"     # Londyn Luton
date_from = "2025-12-01"
date_to = "2025-12-31"
adult_count = 1
use_wdc = True  # True = Wizz Discount Club, False = bez zniżek

# 🔐 Nagłówki (minimum wymagane)
headers = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

# 📦 Payload (request body)
payload = {
    "flightList": [{
        "departureStation": departure_station,
        "arrivalStation": arrival_station,
        "from": date_from,
        "to": date_to
    }],
    "adultCount": adult_count,
    "childCount": 0,
    "infantCount": 0,
    "wdc": use_wdc,
    "flightType": "departure"
}

# 🌍 Wyślij zapytanie
response = requests.post("https://be.wizzair.com/9.1.0/api/search/search", json=payload, headers=headers)

# 🔎 Parsowanie
if response.status_code == 200:
    data = response.json()

    try:
        flights = data.get("outboundFlights", [])
        results = []

        for flight in flights:
            price = flight.get("price", {}).get("amount")
            currency = flight.get("price", {}).get("currencyCode")
            departure_date = flight.get("departureDate")

            if price is not None:
                date_str = datetime.fromisoformat(departure_date).strftime("%Y-%m-%d")
                results.append((date_str, price, currency))

        # 🔽 Posortuj po cenie
        results.sort(key=lambda x: x[1])

        print(f"\n📅 Najtańsze loty {departure_station} ➜ {arrival_station} ({date_from} do {date_to}):\n")
        for date, price, currency in results:
            print(f"{date} → {price} {currency}")

        if not results:
            print("⚠️ Brak lotów w podanym zakresie.")
    except Exception as e:
        print("❌ Błąd przy przetwarzaniu danych:", e)
        print(response.text)
else:
    print(f"❌ Request failed ({response.status_code})")
    print(response.text)
