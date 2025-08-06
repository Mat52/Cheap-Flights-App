from config import ORIGINS, DESTINATIONS, DATESDEPARTURE, DATESBACK
from ryanair import search_flight
from wizzair import search_wizzair_flight
from datetime import datetime
from config import PRICE_THRESHOLD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
import requests


if __name__ == "__main__":
    results = []

    for origin in ORIGINS:
        for country, destinations in DESTINATIONS.items():
            for destination in destinations:
                for date in DATESDEPARTURE:
                    result = search_wizzair_flight(origin, destination, date)
                    if result:
                        results.append(result)


    print("\n📋 ZNALEZIONE POŁĄCZENIA:")
    for r in results:
        print(f"✈️ {r['origin']} -> {r['destination']} | {r['date']} | {r['Airline']} | {r['price']} PLN")



