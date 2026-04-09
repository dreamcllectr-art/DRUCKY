# Pipeline + Signal Quality: 10% Better

**Date:** 2026-03-27
**Scope:** Daily pipeline reliability, runtime, and alpha signal quality
**Goal:** Faster runtime, no stale/false-neutral data, IC-adaptive convergence weights

---

## Problem

Three related issues compound to erode signal quality:

1. **Runtime bloat**: Stocktwits (~700s) and Alpha Vantage (~800s) fetchers use hard-coded `time.sleep()` on rate limits. A single 429 costs a full sleep even if the next request would succeed in 2s.
2. **Silent failures**: 300+ `except: pass` blocks mean module failures are invisible. A failed fetch returns nothing, but the module defaults to score=50 (neutral), which dilutes high-conviction signals in the convergence engine.
3. **IC not wired to weights**: `signal_ic.py` computes Spearman IC per module×horizon×regime, but `convergence_engine.py` uses static weights. The backtester's output is unused.

The common thread: **stale or missing data gets treated as neutral signal instead of absent signal**, which suppresses conviction scores.

---

## Design

### New files

| File | Purpose |
|------|---------|
| `tools/utils/rate_limiter.py` | Exponential backoff + jitter decorator for all API fetchers |
| `tools/utils/module_logger.py` | Structured `log_module_error()` + `get_module_health()` + DB table |
| `tools/utils/data_quality.py` | `check_data_freshness(table, date_col, max_age_days)` per-module staleness gate |

### Modified files

| File | Change |
|------|--------|
| `tools/stocktwits_sentiment.py` | Apply `@rate_limited` decorator, remove hard-coded sleeps |
| `tools/alpha_vantage_technical.py` | Apply `@rate_limited` decorator |
| `tools/fmp_v2.py` | Apply `@rate_limited` decorator |
| `tools/finnhub_news.py` | Apply `@rate_limited` decorator |
| `tools/convergence_engine.py` | IC-adaptive weight overrides at run start |
| All 35 scoring modules | Replace `except: pass` with `log_module_error()`; add freshness check before scoring |

---

## Component Details

### 1. `utils/rate_limiter.py`

```python
@rate_limited(max_retries=4, base_delay=1.0, max_delay=60.0, jitter=True)
def fetch_stocktwits(symbol): ...
```

- Backoff formula: `delay = min(base * 2^attempt + uniform(0, 1), max_delay)`
- Triggers on: HTTP 429, 503, connection errors
- On final retry failure: raises and lets `module_logger` capture it
- No change to caller interface — transparent decorator

### 2. `utils/data_quality.py`

Freshness thresholds (configurable dict):

```python
FRESHNESS_CONFIG = {
    "prices":        1,   # days
    "fundamentals":  7,
    "fmp_v2":        1,
    "stocktwits":    1,
    "alpha_vantage": 1,
    "edgar":         7,
    "finnhub_news":  1,
    "alt_data":      3,
    "macro_fred":    3,
}
```

`check_data_freshness(table, date_col, max_age_days) -> dict`:
- Queries `MAX(date_col)` from the table
- Returns `{"fresh": True/False, "age_days": N, "latest": date}`
- Stale → module returns `None` score (not 50), logs WARNING
- Missing entirely → module returns `None` score, logs CRITICAL

**Key invariant**: stale or missing data produces **absence** in the convergence weighted average, not a false neutral. The convergence engine already handles `None` by excluding the module from the denominator.

### 3. `utils/module_logger.py`

Replaces ~300 silent `except: pass` blocks:

```python
log_module_error(module="stocktwits", phase="fetch", exc=e, severity="WARNING")
```

Writes to a `module_health` table: `(run_date, module, phase, severity, error_msg, ts)`.
`get_module_health(run_date)` returns a summary dict used in the pipeline health check at Phase 4.

### 4. IC-Adaptive Convergence Weights

In `convergence_engine.py`, at the start of `run_convergence()`:

1. Query `signal_ic` table: rolling 60-day Spearman IC per module at 20d horizon, filtered by current macro regime
2. If `n_obs >= 20` for a module:
   - `new_weight = min(max(0, IC) * static_weight * 2, static_weight * 2)`  (floors at 0, caps at 2× static)
   - Negative IC modules get weight = 0 (zeroed, not inverted)
3. Re-normalize all weights to sum to 1.0
4. Log weight overrides to `pipeline_run_log` table for auditability
5. Fallback: if `signal_ic` table empty or regime has <20 obs → use static weights unchanged

---

## Data Flow

```
Fetcher (rate_limited)
  → DB table
  → check_data_freshness()
  → [stale: None score + log] or [fresh: compute score]
  → convergence_engine (IC-weighted, None excluded from denominator)
  → conviction signal
```

---

## Error Handling

- All module exceptions caught by `log_module_error()` — no silent swallowing
- Stale data → None (absent from convergence), not 50 (false neutral)
- Rate limit retries → exponential backoff, final failure logged as CRITICAL
- IC data unavailable → static weights used (safe fallback)
- `module_health` table queryable post-run for pipeline health dashboard

---

## What This Does NOT Change

- Pipeline phase order or checkpointing logic
- Convergence engine scoring formula
- Signal generator entry/stop/target logic
- Database schema (module_health is a new table; no existing tables modified)
- Any frontend code

---

## Success Criteria

1. Stocktwits + Alpha Vantage fetcher wall time drops (fewer wasted full sleeps)
2. Zero silent `except: pass` failures — all errors visible in `module_health`
3. Convergence weights update per-regime from IC data on runs where `signal_ic` has ≥20 obs
4. No module returns score=50 when its data is missing or stale — it returns None and is excluded
