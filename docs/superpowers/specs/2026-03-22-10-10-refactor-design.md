# 10/10 Engineering Refactor — Design Spec

**Date:** 2026-03-22
**Status:** Approved
**Approach:** Hybrid — Phase 1 (security + quality) ships first; Phase 2 (db split) follows; Phase 3 (structural) ships as three independent branches.

---

## Context

The Druckenmiller Alpha System is a 106-module Python quant pipeline + Next.js dashboard backed by PostgreSQL. The system works but has accumulated structural debt:

- API keys hardcoded as fallback values in `config.py` (committed to git)
- `db.py` is 542 lines doing 5 unrelated jobs
- 8 ad-hoc `api_*.py` files with no domain grouping (no v1/v2 split exists; routes grew organically)
- `daily_pipeline.py` uses hardcoded phase numbers (`2.3a`, `2.75`, `2.85`)
- No shared fetcher abstraction — rate limiting and error handling duplicated across 17 modules
- No post-phase data quality checks — phases can "succeed" writing 0 rows

---

## Phase 1: Security + Data Quality

**Risk:** Low. Zero module changes, zero API changes, zero frontend changes.

### 1a — Remove hardcoded API keys

**Problem:** `config.py` uses `os.getenv("KEY", "actual_key_value")` — real keys in source code, committed to git.

**Fix:**
- Strip all default values: `os.getenv("KEY", "")` only
- Add `validate_config()` that logs a warning for each missing key at startup
- Commit an updated `.env.example` listing all key names with no values

**Files changed:** `tools/config.py`, `.env.example`

### 1b — Post-phase row count validation

**Problem:** A phase can raise no exception but write 0 rows. The checkpoint system marks it complete. Silent data gaps propagate downstream.

**Fix:** Add an `@expects_rows(table, min_count=1, date_col="date", max_lag_days=1)` decorator to `daily_pipeline.py`.

After each decorated phase completes, the decorator runs:
```python
SELECT COUNT(*) FROM {table}
WHERE {date_col} >= (CURRENT_DATE - INTERVAL '{max_lag_days} days')::text
```

`max_lag_days=1` for real-time sources (prices, news). `max_lag_days=7` for FRED/macro data where upstream reporting lags are normal. Phases with no `date_col` (e.g., `stock_universe`) skip the date filter entirely.

If count < `min_count`, the phase is re-raised as a failure: `"Phase wrote 0 rows to {table} — check API key or upstream data"`.

**Scope constraint:** First-pass annotation covers only phases with a clear single primary table. Multi-table phases (e.g., `fetch_fmp_v2` writes 4 tables) are left unannotated until Phase 3c establishes the per-table row count contract via `BaseFetcher`.

**Files changed:** `tools/daily_pipeline.py` (decorator definition + annotations on single-table phases only)

---

## Phase 2: db.py Split

**Risk:** Medium. Touches the import structure of 96 modules — mitigated entirely by a compatibility shim.

### New structure

```
tools/db/
  __init__.py    ← loads .env, re-exports everything (backward compat)
  session.py     ← connection pool + wrappers
  query.py       ← query helpers + _to_pg shim
  schema.py      ← TABLE_PKS + init_db() + all DDL
```

The existing `tools/db.py` is replaced by the `tools/db/` package. `__init__.py`:

```python
from dotenv import load_dotenv
load_dotenv()  # must be here — guarantees DATABASE_URL is set before pool init

from tools.db.session import get_conn, _release, _PgConnWrapper, _PgCursorWrapper
from tools.db.query import query, query_df, upsert_many, _to_pg
from tools.db.schema import init_db, TABLE_PKS

__all__ = ["get_conn", "_release", "query", "query_df", "upsert_many",
           "_to_pg", "init_db", "TABLE_PKS", "_PgConnWrapper", "_PgCursorWrapper"]
```

**`load_dotenv()` lives exclusively in `__init__.py`.** Sub-modules (`session.py`, `query.py`, `schema.py`) never call `load_dotenv()` themselves. Direct imports like `from tools.db.session import get_conn` (bypassing `__init__.py`) are prohibited.

Each sub-module must include a fail-fast runtime guard as its first executable line:
```python
import os as _os
assert _os.environ.get("DATABASE_URL"), \
    "Import via 'from tools.db import ...' — do not import sub-modules directly"
```
This makes unauthorized direct imports fail immediately with a clear error rather than silently connecting to the wrong database. `migrate_sqlite_to_pg.py` and all other callers must import via `from tools.db import ...` only.

**Every existing `from tools.db import X` across 96 modules keeps working with zero changes.**

### session.py responsibilities
- `_get_pool()` — lazy-init `ThreadedConnectionPool(2, 30)`
- `_PgCursorWrapper` — wraps psycopg2 cursor, applies `_to_pg()` on execute
- `_PgConnWrapper` — adds `executescript()`, `execute()`, `close()→putconn()` shims
- `get_conn()` → returns `_PgConnWrapper`
- `_release(conn)` → returns connection to pool

### query.py responsibilities
- `_to_pg(sql)` — SQLite→PostgreSQL dialect shim (lives here until all modules are converted)
- `_col_cache`, `_pg_columns()` — column cache for schema-aware upserts
- `query(sql, params)` → list of dicts
- `query_df(sql, params)` → pandas DataFrame
- `upsert_many(table, cols, rows)` → schema-aware batch upsert with auto-ALTER

### schema.py responsibilities
- `TABLE_PKS` — dict mapping 160+ table names to their PK column lists
- `init_db()` — all `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN IF NOT EXISTS`
- No Alembic; idempotent DDL is sufficient for this system

---

## Phase 3: Structural Refactor

**Risk:** Medium-high. Delivered as **three independent branches** — each can be reviewed, merged, and verified separately. System stays live on `main` throughout.

Merge order: **3b first** (lowest risk, pure file moves), then **3c**, then **3a** (highest risk, pipeline logic).

### 3a — Pipeline DAG (`refactor/pipeline-dag`)

**Problem:** `daily_pipeline.py` uses manual phase numbering, hardcoded execution order, and no formal dependency declaration.

**Fix:** Replace with a `Phase` dataclass + `PipelineRunner`.

```python
@dataclass
class Phase:
    name: str                          # human-readable, used as checkpoint key
    fn: Callable                       # the function to run
    deps: list[str] = field(default_factory=list)  # phase names that must complete first
    parallel: bool = True              # can run alongside other ready phases
    min_rows: dict[str, int] = field(default_factory=dict)  # table → min expected rows
```

`PipelineRunner`:
1. Accepts a flat list of `Phase` objects
2. Builds a dependency graph (topological sort — error on cycles)
3. Runs all phases whose deps are satisfied in parallel (`ThreadPoolExecutor`)
4. Checkpoint store: **stays SQLite** (`.tmp/pipeline_checkpoints.db`) with a single-writer lock — a `threading.Lock()` around all checkpoint reads/writes prevents `database is locked` errors under parallel execution. Checkpoint state is intentionally separate from the main Postgres DB.
5. Logs a clean summary table at the end

**Phase definitions** replace the current script body:

```python
PHASES = [
    Phase("universe",     fetch_universe.run,     deps=[]),
    Phase("prices",       fetch_prices.run,       deps=["universe"]),
    Phase("fundamentals", fetch_fundamentals.run, deps=["universe"]),
    Phase("macro",        fetch_macro.run,        deps=[], min_rows={}),  # FRED lag: no daily check
    Phase("news",         fetch_news.run,         deps=["universe"]),
    Phase("tech_score",   technical_scoring.run,  deps=["prices"],
          min_rows={"technical_scores": 500}),
    # ... all phases declared this way
]
```

No more `2.3a`. Phase identity is its name string.

### 3b — API Route Consolidation (`refactor/api-routes`)

**Problem:** 8 `api_*.py` files grew organically with no domain grouping. Route ownership is unclear.

**Fix:**

1. **Audit:** grep `dashboard/src` for all `/api/` fetch calls → produce a complete list of endpoints the frontend actually calls
2. **Delete:** remove any route handler not referenced by the frontend (dead code audit)
3. **Reorganize** into `tools/api/routes/`:

```
tools/api/
  __init__.py       ← FastAPI app, mounts all routers
  routes/
    signals.py      ← /api/v2/signals, /api/v2/convergence, /api/v2/gates, /api/v2/screener
    portfolio.py    ← /api/v2/conviction, /api/v2/performance, /api/v2/risk
    market.py       ← /api/v2/terminal, /api/v2/macro, /api/v2/prices, /api/v2/headlines
    intel.py        ← all intelligence module endpoints
    system.py       ← /api/v2/health, /api/v2/cache/clear, /api/v2/pipeline/status
```

**All URLs preserved.** Only file organization changes. No frontend changes required. Verify by running `grep -r "fetch.*api" dashboard/src` before and after — same set of URLs.

### 3c — BaseFetcher (`refactor/base-fetcher`)

**Problem:** Rate limiting, error handling, retry logic duplicated across 17 fetch modules.

**Fix:** Define `tools/fetchers/base.py`:

```python
class BaseFetcher:
    """Base class for single-table data fetchers.
    Multi-table fetchers should subclass directly and override run()."""

    table: str                  # must set in subclass
    pk_cols: list[str]          # auto-resolved from TABLE_PKS if not set

    def fetch(self) -> list[dict]:
        raise NotImplementedError

    def transform(self, raw: list[dict]) -> list[dict]:
        return raw              # default: passthrough

    def run(self) -> int:
        """Fetch, transform, upsert. Returns row count written."""
        raw = self.fetch()
        rows = self.transform(raw)
        if not rows:
            return 0
        upsert_many(self.table, list(rows[0].keys()), rows)
        return len(rows)
```

**Initial migration — single-table fetchers only:**
- `fetch_alpha_vantage_tech.py` → `AlphaVantageFetcher(BaseFetcher)` (single table: `av_technical_indicators`)
- `fetch_eia_data.py` → `EIAFetcher(BaseFetcher)` (single table: `eia_storage_surprise`)
- `fetch_epo.py` → `EPOFetcher(BaseFetcher)` (single table: `epo_patents`)
- `fetch_finra.py` → `FINRAFetcher(BaseFetcher)` (single table: `finra_short_interest`)
- `fetch_stocktwits.py` → `StockTwitsFetcher(BaseFetcher)` (single table: `stocktwits_sentiment`)

**Explicitly excluded from this pass:**
- `fetch_fmp_v2.py` — writes 4 tables; must override `run()` directly
- `fetch_macro.py` — writes to `macro_indicators` via two separate FRED series dicts; must override `run()` directly

These two remain as plain modules. A future `MultiTableBaseFetcher` can be designed when the pattern is clearer.

---

## Execution Order

```
Phase 1a (security)          → ship immediately, independent
Phase 1b (row counts)        → ship immediately, independent
Phase 2  (db split)          → ship after Phase 1 is stable
Phase 3b (API routes)        → first of Phase 3; lowest risk (pure file moves)
Phase 3c (BaseFetcher)       → second; independent of 3b
Phase 3a (pipeline DAG)      → last; highest risk, needs 2 and 3c stable first
```

---

## Success Criteria

- [ ] No API keys with real default values in any git-tracked file
- [ ] Pipeline phase that writes 0 rows is marked failed (not completed) in checkpoint DB
- [ ] `from tools.db import get_conn, query, upsert_many` works unchanged across all 96 modules
- [ ] `daily_pipeline.py` has no phase numbers; all phases defined as `Phase(name, fn, deps=[...])`
- [ ] 8 `api_*.py` files replaced by `tools/api/routes/` with 5 focused route files
- [ ] All API URLs in `dashboard/src` return HTTP 200 on a running server (verified by grep + smoke test)
- [ ] 5 single-table fetchers are `BaseFetcher` subclasses; `fetch_fmp_v2` and `fetch_macro` explicitly documented as manual overrides
- [ ] Pipeline runs end-to-end with 0 failed checkpoints on a fresh run (all prior-day checkpoint state cleared)
- [ ] Checkpoint SQLite file uses a `threading.Lock()` — no `database is locked` errors under parallel execution
