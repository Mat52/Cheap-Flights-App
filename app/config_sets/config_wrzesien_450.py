from datetime import datetime, timedelta

# 📆 Funkcja generująca daty między start a end (włącznie)
def generate_dates(start: str, end: str):
    start_date = datetime.strptime(start, "%Y-%m-%d")
    end_date = datetime.strptime(end, "%Y-%m-%d")
    delta = (end_date - start_date).days
    return [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(delta + 1)]

# 🌍 Mapowanie kodów lotnisk na miasta
AIRPORT_NAME_HINT = {
    "KRK": "Kraków",
    "KTW": "Katowice",
    "WMI": "Warszawa",
    "POZ": "Poznań",
    "GDN": "Gdańsk",
    "WRO": "Wrocław",
    "MAD": "Madryt",
    "BCN": "Barcelona",
    "AGP": "Malaga",
    "VLC": "Walencja",
    "RAK": "Marrakesz",
    "AGA": "Agadir",
    "LIS": "Lizbona",
    "FAO": "Faro"
}

# ✈️ Grupy miast bazowych i docelowych
GRUPY_BAZ = [
    ["KRK", "KTW"],
]

GRUPY_DESTYNACJI = [
    ["BCN", "GRO"], ["PFO", "LCA"], ["CAG", "OLB"]
]

# 📍 Skąd i dokąd latamy
ORIGINS = ["KRK", "KTW"]

DESTINATIONS = {
  # "egipt": ["HRG", "SSH"],
  # "wyspy kanaryjskie": ["MAD", "VLC", "CDT", "AGP"],
    "hiszpania": ["MAD", "VLC", "CDT", "AGP", "ALC", "SVQ"],
    "francja":["NCE"],
   #"maroko": ["RAK", "AGA"],
   #"portugalia": ["PDL", "FAO", "OPO", "LIS", "FNC"],
   "malta": ["MLA"],
   "cypr": ["LCA", "PFO"],
   "wlochy": ["CAG", "OLB", "AHO", "TPS", "PMO","CTA"],
   "grecja": ["CFU", "RHO", "HER", "CHQ", "JTR"]
}
# , "BCN", "GRO", "MAD", "VLC", "CDT"
# 📆 Zakresy dat
DATESDEPARTURE_RANGE = ("2025-09-05", "2025-09-06")
DATESBACK_RANGE = ("2025-09-08", "2025-09-10")

MIN_DAYS = 3
MAX_DAYS = 10



# 📆 Wygenerowane listy dat
DATESDEPARTURE = generate_dates(*DATESDEPARTURE_RANGE)
DATESBACK = generate_dates(*DATESBACK_RANGE)

# 💰 Maksymalna cena za lot w obie strony:
PRICE_THRESHOLD = 450 # PLN

# 🤖 Telegram powiadomienia
TELEGRAM_BOT_TOKEN = "8203266092:AAE-6N12zaOo05yQuepTjWWC_wrEXZIycyE"
TELEGRAM_CHAT_ID = "6471227110"

# 🗓️ Skróty miesięcy
MONTH_MAP = {
    "01": "sty", "02": "lut", "03": "mar", "04": "kwi",
    "05": "maj", "06": "cze", "07": "lip", "08": "sie",
    "09": "wrz", "10": "paź", "11": "lis", "12": "gru"
}
