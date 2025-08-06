from datetime import datetime

# Mapowanie numerów miesięcy na polskie nazwy
MONTH_MAP = {
    1: "styczeń",
    2: "luty",
    3: "marzec",
    4: "kwiecień",
    5: "maj",
    6: "czerwiec",
    7: "lipiec",
    8: "sierpień",
    9: "wrzesień",
    10: "październik",
    11: "listopad",
    12: "grudzień",
}

# Aktualny miesiąc i rok

def ReturnMonthAndYear():
    now = datetime.now()
    month_name = MONTH_MAP[now.month]
    year = str(now.year)
    return month_name + " " +year

