"""Step 3: SQLite UPSERT, paginated search, and CSV export."""
import sqlite3
import pandas as pd

from paths import DATABASE, CSV

DB_FILE = str(DATABASE)
CSV_FILE = str(CSV)


def connect():
    conn = sqlite3.connect(str(DATABASE), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_database():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facilities (
                facility_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                facility_type TEXT NOT NULL,
                province TEXT NOT NULL,
                city TEXT,
                operator_type TEXT,
                ownership TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facilities_province ON facilities(province)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facilities_type ON facilities(facility_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facilities_owner ON facilities(ownership)")


def save_to_database(valid_records):
    init_database()
    sql = """
        INSERT INTO facilities (facility_id, name, facility_type, province, city,
          operator_type, ownership, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(facility_id) DO UPDATE SET
            name=excluded.name, facility_type=excluded.facility_type,
            province=excluded.province, city=excluded.city,
            operator_type=excluded.operator_type, ownership=excluded.ownership,
            latitude=excluded.latitude, longitude=excluded.longitude
    """
    rows = [tuple(r[k] for k in (
        "facility_id", "name", "facility_type", "province", "city",
        "operator_type", "ownership", "latitude", "longitude"
    )) for r in valid_records]
    with connect() as conn:
        conn.executemany(sql, rows)
        total = conn.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
        df = pd.read_sql_query("SELECT * FROM facilities ORDER BY province, name", conn)
    CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV, index=False)
    return {
        "rows_upserted": len(rows),
        "total_rows_in_sqlite": total,
        "database_file": "data/pakistan_health.db",
        "csv_file": "data/pakistan_health_clean.csv",
    }


def _where(province=None, facility_type=None, ownership=None, query=None):
    conditions, args = [], []
    if province:
        conditions.append("LOWER(province) LIKE LOWER(?)")
        args.append(f"%{province}%")
    if facility_type:
        conditions.append("LOWER(facility_type) = LOWER(?)")
        args.append(facility_type)
    if ownership:
        conditions.append("LOWER(ownership) = LOWER(?)")
        args.append(ownership)
    if query:
        conditions.append("(LOWER(name) LIKE LOWER(?) OR LOWER(COALESCE(city,'')) LIKE LOWER(?) OR LOWER(province) LIKE LOWER(?))")
        args.extend([f"%{query}%"] * 3)
    return (" WHERE " + " AND ".join(conditions)) if conditions else "", args


def fetch_from_database(province=None, facility_type=None, ownership=None, limit=50, query=None, page=1):
    init_database()
    where, params = _where(province, facility_type, ownership, query)
    with connect() as conn:
        results = conn.execute(
            "SELECT * FROM facilities" + where + " ORDER BY province, name LIMIT ? OFFSET ?",
            [*params, limit, (page - 1) * limit],
        ).fetchall()
        return [dict(r) for r in results]


def count_from_database(province=None, facility_type=None, ownership=None, query=None):
    init_database()
    where, params = _where(province, facility_type, ownership, query)
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM facilities" + where, params).fetchone()[0]


def dashboard_summary():
    """Fast dashboard metrics; does not regenerate files or plots."""
    from step1_fetch import PROVINCES
    init_database()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
        types = {row[0]: row[1] for row in conn.execute(
            "SELECT facility_type, COUNT(*) FROM facilities GROUP BY facility_type ORDER BY COUNT(*) DESC")}
        ownership = {row[0]: row[1] for row in conn.execute(
            "SELECT ownership, COUNT(*) FROM facilities GROUP BY ownership ORDER BY COUNT(*) DESC")}
        region_counts = {row[0]: row[1] for row in conn.execute(
            "SELECT province, COUNT(*) FROM facilities GROUP BY province")}
        named = conn.execute("SELECT COUNT(*) FROM facilities WHERE name <> ''").fetchone()[0]
        with_city = conn.execute("SELECT COUNT(*) FROM facilities WHERE city IS NOT NULL AND city <> ''").fetchone()[0]
        with_operator = conn.execute("SELECT COUNT(*) FROM facilities WHERE operator_type IS NOT NULL AND operator_type <> ''").fetchone()[0]
    population = sum(value[2] for value in PROVINCES.values())
    regions = []
    for key, (name, _code, pop) in PROVINCES.items():
        count = region_counts.get(name, 0)
        regions.append({
            "key": key, "name": name, "count": count, "population": pop,
            "per_100k": round(count / pop * 100000, 2),
        })
    regions.sort(key=lambda item: item["count"], reverse=True)
    return {
        "total": total,
        "types": types,
        "ownership": ownership,
        "regions": regions,
        "mapped_regions": sum(r["count"] > 0 for r in regions),
        "national_per_100k": round(total / population * 100000, 2),
        "quality": {
            "named_pct": round(named / total * 100, 1) if total else 0,
            "city_pct": round(with_city / total * 100, 1) if total else 0,
            "operator_pct": round(with_operator / total * 100, 1) if total else 0,
        },
    }
