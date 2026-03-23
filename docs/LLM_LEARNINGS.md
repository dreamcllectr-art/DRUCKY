# System Build Learnings — Druckenmiller Alpha Platform

> Feed this to any LLM working on this codebase to skip months of debugging.
> Two parts: General engineering principles (Section 0) + codebase-specific knowledge (Sections 1-8).
> Updated continuously. Most recent lessons at top of each section.

---

## 0. General Engineering Learnings

These apply to any software system — data pipelines, web apps, APIs, CLIs. Not financial-specific.

### Database Design

- **SQLite is a trap for production systems.** It works fine for prototyping but breaks under concurrency, lacks real types, and silently accepts invalid data. Migrate to Postgres before you have meaningful data, not after.
- **Always define explicit PKs before inserting data.** Adding a unique constraint to a table with duplicates requires deduplication first — painful. Design the constraint before the first insert.
- **SERIAL PKs and upsert don't mix cleanly.** If you need upsert semantics, use a composite natural key as the PK, not a surrogate SERIAL id. If you must use SERIAL, add a `UNIQUE` constraint on the business key columns separately.
- **Schema drift is inevitable.** When code adds columns before the DB migration runs, you get `column X does not exist` errors. Pattern: always wrap new columns in `ALTER TABLE X ADD COLUMN IF NOT EXISTS`. Never assume the DB matches the code.
- **Don't mix SQL dialects.** Date arithmetic, JSON functions, `INSERT OR REPLACE`, `LIMIT` in subqueries — all differ between SQLite, Postgres, MySQL. If you write a SQL abstraction layer, test every query pattern explicitly against the target DB.

### API Integration

- **APIs deprecate without warning.** Always check response status codes AND response body for deprecation messages before assuming an API works. FMP returned 403 with a helpful message — many don't. Build fallbacks for every critical external API.
- **Free tiers have hidden limits.** OpenFIGI allows 100 items/request in docs but returns 413 in practice on free tier — actual limit is 10. Always test at the boundary, not just with small examples.
- **Rate limits compound.** A pipeline hitting 20 APIs × 900 stocks can exhaust rate limits in surprising ways. Add `time.sleep()` between batch calls, log rate limit 429s explicitly, and design for graceful degradation (partial data > crash).
- **Cache aggressively for expensive lookups.** CUSIP → ticker resolution via API is slow and rate-limited. Cache to a local JSON file and only resolve unknowns. A cached map pays for itself immediately.
- **Verify the API field names before building on them.** SEC's `company_tickers_exchange.json` was assumed to have a `cusip` field — it doesn't. Always print the actual response structure before writing code against it.

### Python Concurrency & State

- **Module-level globals for expensive singletons.** DB connection pools, API clients, ML models — initialize once at module level, reuse everywhere. Creating per-call is the #1 cause of connection pool exhaustion.
- **Threading + global state = subtle bugs.** If multiple threads call `init_db()` simultaneously, concurrent DDL on the same table causes race conditions. Protect with `threading.Lock()` + a done flag.
- **Don't store mutable state in function defaults.** `def f(data=[])` is a Python gotcha — the list persists across calls. Use `None` as default and initialize inside.
- **Background processes lose `/tmp` on reboot.** Never store persistent data (DB, cache files) in `/tmp`. Use a project-relative `.tmp/` directory that survives restarts.

### Data Pipeline Design

- **Checkpoint every phase.** Long pipelines (hours) will fail partway through. A checkpoint system (even just a SQLite table of `{date, phase, status}`) lets you resume from the failure point without rerunning everything. Worth building on day one.
- **Fail loudly, skip gracefully.** A module that fails silently (catches all exceptions, returns empty) is worse than one that crashes — you don't know what data is missing. Log the error and the symbol. Let the pipeline continue to other modules but flag the failure.
- **Empty data ≠ no data.** Distinguish between "module ran and found nothing" vs "module failed and returned nothing." Store a sentinel row or a run-log entry so you can tell the difference later.
- **Order matters more than you think.** If Module A's output feeds Module B, and both run in parallel, B gets stale data from the previous run. Make dependency ordering explicit, not assumed.
- **Re-runnable is non-negotiable.** Every module should be safely idempotent — running it twice on the same day should not double-count data. Use `ON CONFLICT DO UPDATE` or `DELETE WHERE date=today` before insert.

### LLM-Assisted Development

- **Give the LLM a way to verify its own work.** The single biggest quality multiplier: tell it to run the code and check the output before declaring success. A closed feedback loop (write → run → observe → fix) produces far better results than one-shot generation.
- **One fix at a time, then verify.** When debugging a chain of errors, fix one, run the test, confirm it's resolved, then move to the next. Batching fixes makes it impossible to know which fix solved which problem.
- **LLMs confidently generate wrong API field names.** Always verify API response structure with a real test call before writing code against it. Never trust the LLM's knowledge of external API schemas — they change.
- **Error messages are the best prompt context.** When something breaks, paste the full stack trace, not a summary. The LLM needs the exact error type, the exact line, and the exact SQL/data to diagnose correctly.
- **LLMs drift toward complexity.** Periodically review generated code for unnecessary abstractions. The right solution is usually simpler than what gets generated when iterating under pressure.
- **Regex on SQL strings is fragile.** The `_to_pg()` function that converts SQLite → Postgres SQL via regex is powerful but has edge cases. When a new query pattern fails, it's almost always a gap in the regex coverage. Add an explicit test case for each new pattern discovered.

### Domain-Agnostic System Design

- **Data staleness must be explicit in every output.** Whether it's financial filings, sensor readings, or user analytics — always annotate outputs with the data timestamp, not the processing timestamp. They are not the same.
- **Score = 0 has two meanings.** "Nothing qualified" vs "the module failed and returned null." These require different responses. Store a run-log entry or sentinel so you can distinguish them later.
- **Cascading filters mask upstream data problems.** If Step 5 filters out 90% of records, you never notice that Step 7's data is missing. Build a separate data health check that validates each data source independently of the pipeline output.
- **"No results" is valid output.** A system that always produces recommendations is broken. The correct output when nothing qualifies is zero results. Don't tune thresholds just to always produce output — that's a false signal factory.
- **Threshold calibration decays.** Thresholds tuned in one environment (high traffic, bull market, summer load) produce wrong results in another (low traffic, bear market, holiday load). Build regime-aware or percentile-based thresholds rather than hardcoded absolutes where possible.

---

## 1. Database Layer (tools/db.py)

### PostgreSQL Migration (SQLite → Postgres)
- **`_to_pg()` is the SQL translator** between SQLite syntax and Postgres. All query strings pass through it. If a query fails, check here first.
- **`TABLE_PKS` dict is mandatory** for every table that uses `upsert_many`. If a table is missing from `TABLE_PKS`, the generated `ON CONFLICT` clause references non-existent constraints and throws `InvalidColumnReference`.
- **`INSERT OR REPLACE/IGNORE`** must be converted to `ON CONFLICT (pk_cols) DO UPDATE SET ...` / `DO NOTHING`. The `_to_pg` function handles this via TABLE_PKS lookup. Tables with `SERIAL id` primary keys cannot use this pattern — they need a separate `UNIQUE` constraint on business key columns.
- **psycopg2 lowercases all column aliases.** `SELECT foo AS marketCap` → access as `r["marketcap"]`, not `r["marketCap"]`. This silently causes KeyErrors.
- **SQLite date arithmetic doesn't translate.** `date(col, '-260 days')` → `(col::date - INTERVAL '260 days')::text`. The `_to_pg` regex handles simple `date('now', ...)` patterns but NOT column-reference date arithmetic.
- **HAVING clause cannot use SELECT aliases in Postgres.** `HAVING ac > 0` fails if `ac` is a SELECT alias. Must repeat the full expression: `HAVING SUM(CASE WHEN ... THEN 1 ELSE 0 END) > 0`.
- **Thread-safe `init_db()`**: Multiple parallel fetch threads calling `init_db()` simultaneously causes concurrent DDL race conditions on table creation. Use `threading.Lock()` + `_init_db_done` flag to run DDL only once.
- **SQLAlchemy engine singleton**: Creating a new `create_engine()` per `query_df()` call exhausts PostgreSQL `max_connections`. Use a module-level `_sa_engine` singleton with `pool_size=5, max_overflow=5`.
- **`UNIQUE` constraints for SERIAL-PK tables**: Tables with `id SERIAL PRIMARY KEY` don't automatically get unique constraints on business key columns. Must `ALTER TABLE ... ADD CONSTRAINT ... UNIQUE (...)` separately, and deduplicate first if data already exists.

### Schema Drift
- After migration, many tables had fewer columns than the code expected. Pattern: `ALTER TABLE X ADD COLUMN IF NOT EXISTS Y TYPE`.
- Check with: `SELECT column_name FROM information_schema.columns WHERE table_name = 'X'`
- Common drift: columns added in Python code but never reflected in the `CREATE TABLE IF NOT EXISTS` DDL (SQLite silently ignored missing columns in some paths).

---

## 2. External API Pitfalls

### FMP (Financial Modeling Prep)
- **`/search` endpoint is legacy-blocked** for API keys created after August 2025. Returns 403 with "Legacy Endpoint" message. Do not use for CUSIP lookup.
- **Use FMP v4 `/profile/{symbol}`** for fundamental data — still works.
- FMP v3 endpoints mostly still work for fundamentals, DCF, analyst data.

### OpenFIGI (Bloomberg CUSIP → Ticker)
- **Free, no API key required.** POST to `https://api.openfigi.com/v3/mapping`
- **Batch size limit is 10** per request (not 100 — 100 returns 413).
- Rate limit: 25 requests/minute without key. Add `time.sleep(0.3)` between batches.
- Filter for US equities: `exchCode in {"US","UN","UA","UF","UW","UT","UP","UV"}` and `securityType in ("Common Stock","ETP")`.
- Fallback: if no US equity found, take first `Common Stock` entry.

### SEC EDGAR 13F Filings
- **`infotable.xml` doesn't exist for all filers.** Many use `form13f_YYYYMMDD.xml` or similar. Don't hardcode the fallback URL.
- **`{acc}-index.json`** returns 404 for some filers. Fallback: fetch `{acc}-index.htm` and parse XML links with regex: `r'href="(/Archives[^"]+\.xml)"'`. Filter out `primary_doc.xml` and paths containing `xslForm`.
- **XML namespace stripping required**: `re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml)` + strip `xsi:` attributes + strip namespace prefixes from element tags.
- SEC enforces User-Agent header: always set `EDGAR_HEADERS = {"User-Agent": "research@example.com"}`.

### SEC `company_tickers_exchange.json`
- Fields are `["cik", "name", "ticker", "exchange"]` — **no CUSIP field**. Do not try to build a CUSIP map from this endpoint.

### Polymarket / OpenFIGI / FRED
- Polymarket Gamma API: free, no key. Endpoint: `https://gamma-api.polymarket.com/events`
- FRED: requires API key. Store in `.env` as `FRED_API_KEY`.
- When passing FRED dates as SQL params, compute the date in Python first: `cutoff = (date.today() - timedelta(days=N)).isoformat()` — do not pass `date('now', '-N days')` as a SQL param because `_to_pg` converts `?` → `%s` and then the date regex can swallow the placeholder.

### Serper (Google Search)
- API key goes in `.env` as `SERPER_API_KEY`. Returns 400 on invalid key (not 401/403).
- Current key as of 2026-03-23: `61c811982571664a6b46339b2a853be9ae043cb9`

---

## 3. Pipeline Architecture

### Checkpoint System
- Pipeline checkpoints stored in `.tmp/pipeline_checkpoints.db` (local SQLite, not Postgres).
- Table: `pipeline_checkpoints(run_date, phase_name, status, duration_seconds, created_at)`
- To force a phase to rerun: `DELETE FROM pipeline_checkpoints WHERE run_date='YYYY-MM-DD' AND phase_name LIKE '%Phase Name%'`
- Phases skip if `status='completed'` for the current `run_date`. Failed phases re-run automatically on next pipeline start.
- **Gate engine must run AFTER all signal modules complete**, otherwise it scores with stale data. If you rerun a signal module manually, also clear the gate engine checkpoint.

### Module Loading Order
- Data fetch phases (1.x) run in parallel threads.
- Signal scoring phases (2.x) run after data is loaded.
- Convergence + gate engine (3.x) run last, after all signal scores exist.
- The gate engine (Phase 3.59) scores every asset in the universe through a 10-gate cascade.

### Gate Engine Logic
- **Gates are sequential**: a stock failing Gate 5 never reaches Gate 7 (smart money), even if smart money score is 100.
- **Gate 5 = Technical Trend**: threshold ~58. In bear markets, most equities fail here. This is by design — smart money holding ≠ good entry.
- **Gate 7 = Smart Money**: threshold 50 conviction_score, OR insider_net > 0, OR capital_flow >= 65, OR smart_mgr_count >= 2.
- **0 fat pitches is normal during market corrections** — it means the system is working correctly, not that data is missing.

### 13F Smart Money Data Flow
1. `filings_13f.py` fetches SEC 13F XML → parses positions → resolves CUSIP → ticker via OpenFIGI → stores in `filings_13f` table.
2. `_smart_money_scores()` aggregates by symbol, computes `conviction_score` using `MANAGER_WEIGHTS` → stores in `smart_money_scores`.
3. Gate engine loads `smart_money_scores` via JOIN to get `smartmoney_score` and `smart_manager_count` per symbol.
4. If `filings_13f` is empty, gates 7+ will never pass for equities.

---

## 4. Common Error Patterns

| Error | Root Cause | Fix |
|---|---|---|
| `InvalidColumnReference: no unique or exclusion constraint` | Table missing from TABLE_PKS or missing UNIQUE constraint | Add to TABLE_PKS + ALTER TABLE ADD CONSTRAINT UNIQUE |
| `column X does not exist` | Schema drift — column in code but not in DB | ALTER TABLE X ADD COLUMN IF NOT EXISTS |
| `not all arguments converted during string formatting` | `_to_pg` regex swallowed a `%s` placeholder | Compute date in Python, don't pass as SQL param |
| `function date(text, unknown) does not exist` | SQLite `date(col, '-N days')` in Postgres | Use `(col::date - INTERVAL 'N days')::text` |
| `column "alias" does not exist` in HAVING | Postgres doesn't allow SELECT aliases in HAVING | Repeat the full expression in HAVING |
| `null value in column "X" violates not-null constraint` | PK column missing from `upsert_many` columns list | Add PK column to columns list and row tuple |
| KeyError `marketCap` | psycopg2 lowercases aliases | Use lowercase key `marketcap` |
| 13F: 0 positions parsed | CUSIP map empty + FMP /search blocked | Use OpenFIGI batch API |
| 13F: XML 404 on `infotable.xml` | Some filers use different XML filename | Parse HTML index to discover actual XML filename |
| XML parse error `unbound prefix` | `xsi:schemaLocation` namespace not stripped | Add `re.sub(r'\s+xsi:\w+="[^"]*"', '', xml)` |
| `pg_type_typname_nsp_index` race condition | Concurrent `init_db()` from multiple threads | Use threading.Lock + _init_db_done flag |
| PostgreSQL max_connections exhausted | New SQLAlchemy engine per `query_df` call | Use module-level `_sa_engine` singleton |

---

## 5. Development Workflow

### Python Environment
- **NEVER use the iCloud venv at `venv/`** — iCloud evicts compiled `.so` files, breaking pandas/numpy.
- Always use: `/tmp/druck_venv/bin/python`
- If `/tmp/druck_venv` doesn't exist: `python3 -m venv /tmp/druck_venv && /tmp/druck_venv/bin/pip install -r requirements.txt`

### File Reading
- Some files show as "1 line" in the Read tool (iCloud stubs). Use `bash head/grep` instead.

### Testing a Module
```bash
cd "/Users/jurgis/Claude Code/Druckemiller"
/tmp/druck_venv/bin/python -u -m tools.MODULE_NAME 2>&1 | head -50
```

### Verifying DB State
```python
from tools.db import query
rows = query("SELECT COUNT(*) as cnt FROM table_name WHERE date >= '2026-03-01'")
print(rows[0]['cnt'])
```

### Clearing Checkpoints for Rerun
```python
import sqlite3
conn = sqlite3.connect('.tmp/pipeline_checkpoints.db')
conn.execute("DELETE FROM pipeline_checkpoints WHERE run_date='YYYY-MM-DD' AND phase_name LIKE '%Phase X%'")
conn.commit()
```

---

## 6. Data Quality Rules

- **13F data is 45-135 days stale by law.** Never use for current positioning. Always cite `period_of_report`, not filing date.
- **Smart money scores** aggregate across all tracked managers. A score of 0 means no manager holds the stock — not that no data exists.
- **Gate 7 requires smart money data to be populated.** After fresh 13F run, always verify `SELECT COUNT(*) FROM filings_13f WHERE period_of_report >= '2025-01-01'` returns > 0.
- **Polymarket data** feeds the `prediction_markets` module. Gemini JSON parsing occasionally fails — this is non-fatal. The module continues with partial results.
- **Technical scores drop during market corrections** — this causes 0 fat pitches. This is correct behavior, not a data issue.

---

## 7. Tracked 13F Managers

| CIK | Manager | Weight |
|---|---|---|
| 0001536411 | Duquesne (Druckenmiller) | 1.0 |
| 0001649339 | Scion (Burry) | 0.90 |
| 0000813672 | Appaloosa (Tepper) | 0.85 |
| 0001336920 | Pershing Square (Ackman) | 0.85 |
| 0001167483 | Tiger Global | 0.75 |
| 0001336528 | Coatue | 0.75 |
| 0001103804 | Viking Global | 0.75 |

- Appaloosa and Pershing Square often return "No 13F" — they sometimes file confidentially or use different structures.
- Duquesne and Viking: their XML is NOT at `infotable.xml` — use HTML index parsing to find the correct file.

---

## 8. Module Weights in Convergence Engine

From `config_modules.py` — approximate weights:
- smartmoney: 0.08, worldview: 0.07, variant: 0.06, research: 0.05
- news_displacement: 0.05, foreign_intel: 0.04, pairs: 0.03
- prediction_markets: 0.02, pattern_options: 0.03, estimate_momentum: 0.04
- ma: 0.04, energy_intel: 0.03, alt_data: 0.03
- Fundamentals feeds Gate 6 directly (not convergence score)

---

_Last updated: 2026-03-23_
