# SQLite → PostgreSQL Migration Design
**Date:** 2026-03-22
**Status:** Approved

## Goal
Replace SQLite with PostgreSQL everywhere — local dev and Hetzner production. Same code, same behavior, no dual-mode complexity.

## Architecture

### `tools/db.py` — full replacement, same API
Four functions, same signatures as today:
- `get_conn()` — returns a psycopg2 connection from a `ThreadedConnectionPool` (min 2, max 10)
- `init_db()` — creates all tables via PostgreSQL DDL; `ADD COLUMN IF NOT EXISTS` for migrations
- `query(sql, params)` — returns `list[dict]` using `RealDictCursor`; `%s` placeholders
- `query_df(sql, params)` — returns `pd.DataFrame` via SQLAlchemy engine on same `DATABASE_URL`
- `upsert_many(table, columns, rows)` — `INSERT ... ON CONFLICT (pk_cols) DO UPDATE SET ...` using a `TABLE_PKS` lookup dict

### Connection
`DATABASE_URL` env var: `postgresql://user:password@host:5432/druckenmiller`

### Schema conversions from SQLite
| SQLite | PostgreSQL |
|--------|-----------|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` |
| `datetime('now')` | `NOW()` |
| `?` params | `%s` params |
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT DO UPDATE` |
| `ALTER TABLE ADD COLUMN` + try/except | `ALTER TABLE ADD COLUMN IF NOT EXISTS` |
| `executescript()` | individual `execute()` calls |

### `upsert_many()` strategy
A `TABLE_PKS` dict maps every table to its primary key column(s). For tables with `AUTOINCREMENT` PKs (`id` column), we upsert on the unique business key columns instead and add appropriate `UNIQUE` constraints.

## Migration Script
`tools/migrate_sqlite_to_pg.py` — one-time script:
1. Open SQLite read connection
2. For each table: read all rows in batches of 1000
3. Write to Postgres via `upsert_many()`
4. Log row counts before/after for verification

## Local Dev Setup
```bash
docker run -d --name druck-pg \
  -e POSTGRES_DB=druckenmiller \
  -e POSTGRES_USER=druck \
  -e POSTGRES_PASSWORD=druck \
  -p 5432:5432 postgres:16
```
Add to `.env`:
```
DATABASE_URL=postgresql://druck:druck@localhost:5432/druckenmiller
```

## Dependencies to add
- `psycopg2-binary>=2.9`
- `sqlalchemy>=2.0`

## Files changed
1. `tools/db.py` — full replacement
2. `tools/migrate_sqlite_to_pg.py` — new migration script
3. `requirements.txt` — add psycopg2-binary, sqlalchemy
4. `.env` — add DATABASE_URL (local)
5. `docs/superpowers/specs/` — this file

## Files NOT changed
All pipeline tools (`tools/*.py`) and API files (`tools/api*.py`) — they import `from tools.db import query, upsert_many` and will work transparently.

## Rollback
Keep `.tmp/druckenmiller.db` intact during migration. If Postgres fails, revert `tools/db.py` from git.
