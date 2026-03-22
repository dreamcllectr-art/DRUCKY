"""One-time migration: copy all data from SQLite → PostgreSQL.

Usage:
    cd ~/druckenmiller
    /tmp/druck_venv/bin/python -m tools.migrate_sqlite_to_pg

Requires:
    - DATABASE_URL set in .env pointing to running Postgres
    - .tmp/druckenmiller.db exists (SQLite source)
"""
import os, sqlite3, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.db import upsert_many, get_conn as pg_conn, _release, TABLE_PKS

SQLITE_PATH = os.path.join(Path(__file__).parent.parent, ".tmp", "druckenmiller.db")
BATCH_SIZE = 1000

# Tables with SERIAL pks — insert directly preserving the id values
SERIAL_TABLES = {
    "portfolio", "intelligence_reports", "thematic_ideas",
    "energy_supply_anomalies", "journal_entries",
}


def get_sqlite_tables(lite):
    cur = lite.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def migrate_table(lite, table):
    cur = lite.execute(f"SELECT * FROM {table} LIMIT 1")
    if cur.description is None:
        print(f"  {table}: empty, skip")
        return 0
    columns = [d[0] for d in cur.description]

    total = lite.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if total == 0:
        print(f"  {table}: 0 rows, skip")
        return 0

    migrated = 0
    if table in SERIAL_TABLES:
        # Insert via raw psycopg2 preserving id
        conn = pg_conn()
        try:
            import psycopg2.extras
            col_str = ", ".join(f'"{c}"' for c in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            sql = (
                f'INSERT INTO {table} ({col_str}) VALUES ({placeholders}) '
                f'ON CONFLICT DO NOTHING'
            )
            offset = 0
            while True:
                batch = lite.execute(
                    f"SELECT * FROM {table} LIMIT {BATCH_SIZE} OFFSET {offset}"
                ).fetchall()
                if not batch:
                    break
                rows = [tuple(r) for r in batch]
                with conn.cursor() as c:
                    psycopg2.extras.execute_batch(c, sql, rows)
                conn.commit()
                migrated += len(rows)
                offset += BATCH_SIZE
        finally:
            _release(conn)
    else:
        offset = 0
        while True:
            batch = lite.execute(
                f"SELECT * FROM {table} LIMIT {BATCH_SIZE} OFFSET {offset}"
            ).fetchall()
            if not batch:
                break
            rows = [tuple(r) for r in batch]
            upsert_many(table, columns, rows)
            migrated += len(rows)
            offset += BATCH_SIZE

    print(f"  {table}: {total} → {migrated} rows migrated")
    return migrated


def main():
    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: SQLite DB not found at {SQLITE_PATH}")
        sys.exit(1)

    lite = sqlite3.connect(SQLITE_PATH)
    lite.row_factory = sqlite3.Row
    tables = get_sqlite_tables(lite)
    print(f"Found {len(tables)} tables in SQLite. Starting migration...\n")

    total_rows = 0
    errors = []
    for table in tables:
        try:
            n = migrate_table(lite, table)
            total_rows += n
        except Exception as e:
            print(f"  {table}: ERROR — {e}")
            errors.append((table, str(e)))

    lite.close()
    print(f"\nMigration complete. {total_rows} total rows migrated.")
    if errors:
        print(f"\nErrors ({len(errors)} tables):")
        for t, e in errors:
            print(f"  {t}: {e}")
    else:
        print("No errors.")


if __name__ == "__main__":
    main()
