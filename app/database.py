import psycopg2

DB_CONFIG = {
    "dbname": "flights",
    "user": "user",
    "password": "password",
    "host": "localhost",
    "port": "5432",
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS flights (
        id SERIAL PRIMARY KEY,
        origin TEXT,
        destination TEXT,
        price REAL,
        date TEXT
    )
    """)
    conn.commit()
    conn.close()

def add_flight(origin, destination, price, date):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO flights (origin, destination, price, date) VALUES (%s, %s, %s, %s)",
        (origin, destination, price, date)
    )
    conn.commit()
    conn.close()

def get_all_flights():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flights")
    flights = cursor.fetchall()
    conn.close()
    return flights

if __name__ == "__main__":
    init_db()
    add_flight("WAW", "LON", 299.99, "2025-08-06")
    print(get_all_flights())
