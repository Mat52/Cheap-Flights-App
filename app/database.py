import os

import psycopg2

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "flights"),
    "user": os.getenv("DB_USER", "user"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS flights (
            id SERIAL PRIMARY KEY,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            price REAL NOT NULL,
            date TEXT NOT NULL,
            airline TEXT,
            departure TEXT,
            arrival TEXT,
            scraped_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """)
        # keeps search_flights() fast even once this table has years of history
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_flights_route ON flights (origin, destination)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_flights_date ON flights (date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_flights_price ON flights (price)")
        conn.commit()
    finally:
        conn.close()


def add_flight(origin, destination, price, date, airline=None, departure=None, arrival=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO flights (origin, destination, price, date, airline, departure, arrival)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (origin, destination, price, date, airline, departure, arrival),
        )
        conn.commit()
    finally:
        conn.close()


def save_flight_result(result: dict):
    """Persist one scraped flight dict, as produced by search_flight_google()."""
    add_flight(
        origin=result["origin"],
        destination=result["destination"],
        price=result["price"],
        date=result["date"],
        airline=result.get("Airline"),
        departure=result.get("departure"),
        arrival=result.get("arrival"),
    )


def get_recent_flight(origin, destination, date, max_age_minutes=30):
    """Return the most recently scraped flight for this exact one-way leg
    (origin, destination, date) if it was scraped within the last
    `max_age_minutes` minutes, else None.

    This is the search's cache: a live search checks this before scraping a
    leg from Google Flights, so re-running an overlapping search shortly
    after doesn't repeat work that's still fresh. Best-effort like the rest
    of this module — if the DB is unreachable, callers just treat it as a
    cache miss and scrape live.
    """
    try:
        conn = get_connection()
    except Exception as e:
        print(f"⚠️ Baza niedostępna, pomijam cache dla {origin}->{destination} {date}: {e}")
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT origin, destination, date, price, airline, departure, arrival
               FROM flights
               WHERE origin = %s AND destination = %s AND date = %s
                 AND scraped_at >= NOW() - make_interval(mins => %s)
               ORDER BY scraped_at DESC
               LIMIT 1""",
            (origin, destination, date, max_age_minutes),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return None
    return {
        "origin": row[0], "destination": row[1], "date": row[2], "price": row[3],
        "Airline": row[4], "departure": row[5], "arrival": row[6],
    }


def get_last_price(origin, destination, date):
    """Return the most recently scraped price for this exact one-way leg,
    with no freshness window (unlike get_recent_flight) — used by
    price_watcher.py to detect whether a newly-scraped price differs from
    the last one it saw, however long ago that was. None if this leg has
    never been scraped before.
    """
    try:
        conn = get_connection()
    except Exception as e:
        print(f"⚠️ Baza niedostępna, nie mogę porównać ceny dla {origin}->{destination} {date}: {e}")
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT price FROM flights
               WHERE origin = %s AND destination = %s AND date = %s
               ORDER BY scraped_at DESC
               LIMIT 1""",
            (origin, destination, date),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def get_all_flights():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM flights ORDER BY scraped_at DESC")
        return cursor.fetchall()
    finally:
        conn.close()


def search_flights(origins=None, destinations=None, max_price=None, date_from=None, date_to=None, limit=2000):
    """Instantly query flights already scraped and saved by a previous live
    search — a plain indexed SELECT, no browser/network involved, so this is
    always fast regardless of how a live Google Flights scrape is performing.

    origins/destinations are combined into one "airports of interest" set and
    matched on BOTH ends of a leg (not origin-only / destination-only): a
    round trip's return leg has origin and destination swapped from the
    outbound leg, so a direction-strict filter would only ever find one half
    of a pair and round-trip pairing would silently come up empty.

    Returns a list of dicts shaped like search_flight_google()'s output, so
    the same round-trip pairing logic (core.search.znajdz_polaczenia_dwustronne)
    works on either live or saved results unmodified.
    """
    clauses = []
    params = []
    airports = list(dict.fromkeys((origins or []) + (destinations or [])))  # dedup, keep order
    if airports:
        clauses.append("origin = ANY(%s) AND destination = ANY(%s)")
        params.append(airports)
        params.append(airports)
    if max_price is not None:
        clauses.append("price <= %s")
        params.append(max_price)
    if date_from:
        clauses.append("date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("date <= %s")
        params.append(date_to)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT origin, destination, date, price, airline, departure, arrival
                FROM flights
                {where}
                ORDER BY scraped_at DESC
                LIMIT %s""",
            params,
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    return [
        {
            "origin": r[0], "destination": r[1], "date": r[2], "price": r[3],
            "Airline": r[4], "departure": r[5], "arrival": r[6],
        }
        for r in rows
    ]


if __name__ == "__main__":
    init_db()
    add_flight("WAW", "LON", 299.99, "2025-08-06")
    print(get_all_flights())
