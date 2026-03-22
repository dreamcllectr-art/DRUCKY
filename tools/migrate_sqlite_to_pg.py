"""One-time migration: copy all data from SQLite → PostgreSQL.

Usage:
    cd ~/druckenmiller
    /tmp/druck_venv/bin/python -m tools.migrate_sqlite_to_pg

Requires:
    - DATABASE_URL set in .env pointing to running Postgres
    - .tmp/druckenmiller.db exists (SQLite source)

Strategy:
    - For each SQLite table, check which columns exist in Postgres.
    - Only migrate the intersection of columns (handles schema drift safely).
    - Tables that don't exist in Postgres at all are skipped.
    - Conflict resolution uses PKs from Postgres information_schema when the
      table is not in TABLE_PKS (falls back to ON CONFLICT DO NOTHING).
"""
import os, sqlite3, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2.extras
from tools.db import get_conn as pg_conn, _release, TABLE_PKS

SQLITE_PATH = os.path.join(Path(__file__).parent.parent, ".tmp", "druckenmiller.db")
BATCH_SIZE = 1000


def get_sqlite_tables(lite):
    cur = lite.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def get_postgres_columns(pg, table):
    """Return ordered list of column names for a Postgres table, or None if absent."""
    with pg.cursor() as cur:
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = %s
               ORDER BY ordinal_position""",
            [table],
        )
        rows = cur.fetchall()
        return [r[0] for r in rows] if rows else None


def get_postgres_pks(pg, table):
    """Return list of PK column names from Postgres information_schema."""
    with pg.cursor() as cur:
        cur.execute(
            """SELECT kcu.column_name
               FROM information_schema.table_constraints tc
               JOIN information_schema.key_column_usage kcu
                 ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
               WHERE tc.constraint_type = 'PRIMARY KEY'
                 AND tc.table_schema = 'public'
                 AND tc.table_name = %s
               ORDER BY kcu.ordinal_position""",
            [table],
        )
        return [r[0] for r in cur.fetchall()]


def migrate_table(lite, pg, table):
    # Get SQLite column names
    cur = lite.execute(f"SELECT * FROM {table} LIMIT 1")
    if cur.description is None:
        print(f"  {table}: empty SQLite table, skip")
        return 0
    sqlite_cols = [d[0] for d in cur.description]

    total = lite.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if total == 0:
        print(f"  {table}: 0 rows, skip")
        return 0

    # Get Postgres columns — skip tables that don't exist
    pg_cols = get_postgres_columns(pg, table)
    if not pg_cols:
        print(f"  {table}: not in Postgres schema, skip")
        return 0

    # Intersect: only columns present in both, preserving SQLite order
    pg_cols_set = set(pg_cols)
    cols = [c for c in sqlite_cols if c in pg_cols_set]
    if not cols:
        print(f"  {table}: no overlapping columns, skip")
        return 0

    dropped = set(sqlite_cols) - set(cols)
    if dropped:
        print(f"  {table}: skipping {len(dropped)} extra SQLite cols: {sorted(dropped)}")

    # Build ON CONFLICT clause
    pk_cols = TABLE_PKS.get(table) or get_postgres_pks(pg, table)
    col_str = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    if pk_cols and all(p in cols for p in pk_cols):
        conflict_cols = ", ".join(pk_cols)
        update_cols = [c for c in cols if c not in pk_cols]
        if update_cols:
            update_str = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            on_conflict = f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_str}"
        else:
            on_conflict = f"ON CONFLICT ({conflict_cols}) DO NOTHING"
    else:
        on_conflict = "ON CONFLICT DO NOTHING"

    sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders}) {on_conflict}"

    # Get column indices from SQLite result
    col_indices = [sqlite_cols.index(c) for c in cols]
    # Indices of PK columns within our filtered col list (for NULL filtering)
    pk_indices_in_cols = [cols.index(p) for p in pk_cols if p in cols] if pk_cols else []

    migrated = 0
    skipped = 0
    offset = 0
    while True:
        batch = lite.execute(
            f"SELECT * FROM {table} LIMIT {BATCH_SIZE} OFFSET {offset}"
        ).fetchall()
        if not batch:
            break
        rows = []
        for row in batch:
            values = tuple(row[i] for i in col_indices)
            # Skip rows with NULL in any PK column
            if pk_indices_in_cols and any(values[i] is None for i in pk_indices_in_cols):
                skipped += 1
                continue
            rows.append(values)
        if rows:
            try:
                with pg.cursor() as c:
                    psycopg2.extras.execute_batch(c, sql, rows)
                pg.commit()
                migrated += len(rows)
            except Exception:
                pg.rollback()
                # Fall back to row-by-row to skip bad rows
                for row in rows:
                    try:
                        with pg.cursor() as c:
                            c.execute(sql, row)
                        pg.commit()
                        migrated += 1
                    except Exception:
                        pg.rollback()
                        skipped += 1
        offset += BATCH_SIZE
    if skipped:
        print(f"    (skipped {skipped} rows with NULL in PK columns)")

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

    pg = pg_conn()
    total_rows = 0
    errors = []
    for table in tables:
        try:
            n = migrate_table(lite, pg, table)
            total_rows += n
        except Exception as e:
            pg.rollback()
            print(f"  {table}: ERROR — {e}")
            errors.append((table, str(e)))

    _release(pg)
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
