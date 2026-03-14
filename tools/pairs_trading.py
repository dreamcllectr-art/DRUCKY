"""Pairs Trading / Statistical Arbitrage Module.

Two signal types:
  1. Mean-Reversion — cointegrated pairs where spread z-score exceeds ±2σ.
     Market-neutral long/short trades expecting mean reversion.
  2. Runner Detection — when one leg of a correlated pair diverges with strong
     technicals + fundamentals, flag it as a momentum breakout candidate.

Feeds a pairs_score (0-100) into the convergence engine as the 11th module.
"""

import logging
import math
from datetime import date, datetime, timedelta
from itertools import combinations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

from tools.db import get_conn, query, query_df, upsert_many
from tools.config import (
    PAIRS_MIN_CORRELATION,
    PAIRS_COINT_PVALUE,
    PAIRS_HALF_LIFE_MIN,
    PAIRS_HALF_LIFE_MAX,
    PAIRS_ZSCORE_MR_THRESHOLD,
    PAIRS_ZSCORE_RUNNER_THRESHOLD,
    PAIRS_RUNNER_MIN_TECH,
    PAIRS_RUNNER_MIN_FUND,
    PAIRS_LOOKBACK_DAYS,
    PAIRS_REFRESH_DAYS,
    PAIRS_MIN_PRICE_DAYS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_sector_groups() -> dict[str, list[str]]:
    """Group symbols by sector from stock_universe.

    Returns: {sector: [symbol, ...]}
    """
    rows = query("""
        SELECT symbol, sector FROM stock_universe
        WHERE sector IS NOT NULL AND sector != ''
    """)
    groups: dict[str, list[str]] = {}
    for r in rows:
        groups.setdefault(r["sector"], []).append(r["symbol"])
    return groups


def _load_price_matrix(min_days: int = 120) -> pd.DataFrame:
    """Load closing prices as a wide DataFrame (date × symbol).

    Only includes symbols with at least `min_days` of data.
    Forward-fills gaps up to 5 days, drops symbols with >10% missing.
    """
    df = query_df("""
        SELECT symbol, date, close FROM price_data
        WHERE close IS NOT NULL
        ORDER BY date
    """)
    if df.empty:
        return pd.DataFrame()

    pivot = df.pivot_table(index="date", columns="symbol", values="close")
    pivot = pivot.sort_index()

    # Forward-fill small gaps (weekends, holidays)
    pivot = pivot.ffill(limit=5)

    # Drop symbols with too few data points or too many gaps
    min_count = min_days
    valid_cols = pivot.columns[pivot.count() >= min_count]
    pivot = pivot[valid_cols]

    # Drop symbols with >10% missing after ffill
    threshold = len(pivot) * 0.9
    pivot = pivot.dropna(axis=1, thresh=int(threshold))

    return pivot


def _load_technical_scores() -> dict[str, float]:
    """Load latest technical total_score per symbol."""
    rows = query("""
        SELECT t.symbol, t.total_score
        FROM technical_scores t
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM technical_scores GROUP BY symbol) m
        ON t.symbol = m.symbol AND t.date = m.mx
        WHERE t.total_score IS NOT NULL
    """)
    return {r["symbol"]: r["total_score"] for r in rows}


def _load_fundamental_scores() -> dict[str, float]:
    """Load latest fundamental total_score per symbol."""
    rows = query("""
        SELECT f.symbol, f.total_score
        FROM fundamental_scores f
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM fundamental_scores GROUP BY symbol) m
        ON f.symbol = m.symbol AND f.date = m.mx
        WHERE f.total_score IS NOT NULL
    """)
    return {r["symbol"]: r["total_score"] for r in rows}


# ---------------------------------------------------------------------------
# Statistical computations
# ---------------------------------------------------------------------------

def _compute_hedge_ratio(price_a: pd.Series, price_b: pd.Series) -> float:
    """OLS hedge ratio: log(price_a) = β * log(price_b) + α."""
    log_a = np.log(price_a.dropna())
    log_b = np.log(price_b.dropna())
    common = log_a.index.intersection(log_b.index)
    if len(common) < 30:
        return float("nan")
    X = add_constant(log_b.loc[common].values)
    y = log_a.loc[common].values
    result = OLS(y, X).fit()
    return float(result.params[1])  # β coefficient


def _compute_half_life(spread: pd.Series) -> float:
    """Ornstein-Uhlenbeck half-life from AR(1) on spread.

    spread_t - spread_{t-1} = φ * spread_{t-1} + ε
    half_life = -log(2) / log(1 + φ)
    """
    spread = spread.dropna()
    if len(spread) < 30:
        return float("nan")

    lag = spread.shift(1)
    delta = spread - lag
    # Drop NaN from shift
    valid = ~(lag.isna() | delta.isna())
    lag_vals = lag[valid].values
    delta_vals = delta[valid].values

    if len(lag_vals) < 20:
        return float("nan")

    X = add_constant(lag_vals)
    result = OLS(delta_vals, X).fit()
    phi = result.params[1]

    if phi >= 0:
        return float("nan")  # Not mean-reverting

    half_life = -math.log(2) / math.log(1 + phi)
    return float(half_life)


def _check_staleness() -> bool:
    """Check if pair_relationships need recomputing."""
    rows = query("""
        SELECT MAX(last_updated) as latest FROM pair_relationships
    """)
    if not rows or rows[0]["latest"] is None:
        return True
    try:
        latest = datetime.strptime(rows[0]["latest"], "%Y-%m-%d").date()
        return (date.today() - latest).days >= PAIRS_REFRESH_DAYS
    except (ValueError, TypeError):
        return True


# ---------------------------------------------------------------------------
# Pair relationship computation
# ---------------------------------------------------------------------------

def _compute_pair_statistics(
    price_matrix: pd.DataFrame,
    sector_groups: dict[str, list[str]],
) -> list[dict]:
    """Compute correlation, cointegration, hedge ratio, half-life for intra-sector pairs.

    Only tests pairs with 60d correlation > PAIRS_MIN_CORRELATION.
    Returns list of pair dicts.
    """
    results = []
    available = set(price_matrix.columns)
    today_str = date.today().isoformat()

    total_tested = 0
    total_coint = 0

    for sector, symbols in sector_groups.items():
        # Filter to symbols with price data
        syms = sorted([s for s in symbols if s in available])
        if len(syms) < 2:
            continue

        # Use last LOOKBACK_DAYS for analysis
        pm = price_matrix[syms].iloc[-PAIRS_LOOKBACK_DAYS:]
        if len(pm) < PAIRS_MIN_PRICE_DAYS:
            continue

        for sym_a, sym_b in combinations(syms, 2):
            # Ensure lexicographic ordering
            if sym_a > sym_b:
                sym_a, sym_b = sym_b, sym_a

            pa = pm[sym_a].dropna()
            pb = pm[sym_b].dropna()
            common = pa.index.intersection(pb.index)

            if len(common) < PAIRS_MIN_PRICE_DAYS:
                continue

            pa_c = pa.loc[common]
            pb_c = pb.loc[common]

            # 60-day and 120-day correlations
            corr_60 = pa_c.iloc[-60:].corr(pb_c.iloc[-60:]) if len(common) >= 60 else float("nan")
            corr_120 = pa_c.iloc[-120:].corr(pb_c.iloc[-120:]) if len(common) >= 120 else float("nan")

            # Pre-filter: skip expensive cointegration test if correlation too low
            if math.isnan(corr_60) or corr_60 < PAIRS_MIN_CORRELATION:
                continue

            total_tested += 1

            # Engle-Granger cointegration test
            try:
                _, pvalue, _ = coint(pa_c.values, pb_c.values)
            except Exception:
                continue

            if pvalue > PAIRS_COINT_PVALUE:
                continue

            # Hedge ratio
            hedge = _compute_hedge_ratio(pa_c, pb_c)
            if math.isnan(hedge):
                continue

            # Spread and half-life
            log_spread = np.log(pa_c) - hedge * np.log(pb_c)
            half_life = _compute_half_life(log_spread)

            if math.isnan(half_life):
                continue
            if half_life < PAIRS_HALF_LIFE_MIN or half_life > PAIRS_HALF_LIFE_MAX:
                continue

            total_coint += 1

            results.append({
                "symbol_a": sym_a,
                "symbol_b": sym_b,
                "sector": sector,
                "correlation_60d": round(corr_60, 4),
                "correlation_120d": round(corr_120, 4) if not math.isnan(corr_120) else None,
                "cointegration_pvalue": round(pvalue, 6),
                "hedge_ratio": round(hedge, 4),
                "half_life_days": round(half_life, 1),
                "spread_mean": round(float(log_spread.mean()), 6),
                "spread_std": round(float(log_spread.std()), 6),
                "last_updated": today_str,
            })

    print(f"  Tested {total_tested} pairs, found {total_coint} cointegrated")
    return results


# ---------------------------------------------------------------------------
# Daily spread computation
# ---------------------------------------------------------------------------

def _compute_daily_spreads(
    pairs: list[dict],
    price_matrix: pd.DataFrame,
) -> list[dict]:
    """Compute daily spread z-scores for cointegrated pairs."""
    results = []
    today_str = date.today().isoformat()

    for p in pairs:
        sym_a, sym_b = p["symbol_a"], p["symbol_b"]
        hedge = p["hedge_ratio"]

        if sym_a not in price_matrix.columns or sym_b not in price_matrix.columns:
            continue

        pa = price_matrix[sym_a].dropna()
        pb = price_matrix[sym_b].dropna()
        common = pa.index.intersection(pb.index)

        if len(common) < 60:
            continue

        pa_c = pa.loc[common]
        pb_c = pb.loc[common]

        # Log spread
        log_spread = np.log(pa_c) - hedge * np.log(pb_c)

        # Rolling 60-day z-score
        rolling_mean = log_spread.rolling(60).mean()
        rolling_std = log_spread.rolling(60).std()
        zscore = (log_spread - rolling_mean) / rolling_std

        # Percentile (where current spread sits in full history)
        current_spread = float(log_spread.iloc[-1])
        spread_percentile = float((log_spread < current_spread).mean() * 100)

        # Only store last 5 days of spreads (most recent)
        recent = zscore.iloc[-5:]
        for dt, z in recent.items():
            if pd.isna(z):
                continue
            dt_str = str(dt)[:10] if not isinstance(dt, str) else dt
            results.append({
                "symbol_a": sym_a,
                "symbol_b": sym_b,
                "date": dt_str,
                "spread_raw": round(float(log_spread.loc[dt]), 6),
                "spread_zscore": round(float(z), 4),
                "spread_percentile": round(spread_percentile, 1),
            })

    return results


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

def _generate_mean_reversion_signals(
    pairs: list[dict],
    price_matrix: pd.DataFrame,
) -> list[dict]:
    """Generate mean-reversion signals for pairs with |z-score| > threshold."""
    signals = []
    today_str = date.today().isoformat()

    for p in pairs:
        sym_a, sym_b = p["symbol_a"], p["symbol_b"]
        hedge = p["hedge_ratio"]

        if sym_a not in price_matrix.columns or sym_b not in price_matrix.columns:
            continue

        pa = price_matrix[sym_a].dropna()
        pb = price_matrix[sym_b].dropna()
        common = pa.index.intersection(pb.index)

        if len(common) < 60:
            continue

        pa_c = pa.loc[common]
        pb_c = pb.loc[common]

        log_spread = np.log(pa_c) - hedge * np.log(pb_c)
        rolling_mean = log_spread.rolling(60).mean()
        rolling_std = log_spread.rolling(60).std()
        zscore = (log_spread - rolling_mean) / rolling_std

        current_z = float(zscore.iloc[-1])

        if pd.isna(current_z) or abs(current_z) < PAIRS_ZSCORE_MR_THRESHOLD:
            continue

        # Score: z=2 → 50, z=4 → 100, capped at 100
        raw_score = min(100, abs(current_z) * 25)

        # Half-life bonus: faster reversion = higher score
        hl = p["half_life_days"]
        if hl < 30:
            raw_score = min(100, raw_score * 1.2)

        # Direction
        if current_z > 0:
            direction = "long_b_short_a"  # spread too wide, A overvalued vs B
        else:
            direction = "long_a_short_b"  # spread too narrow, B overvalued vs A

        narrative = (
            f"Mean-reversion: {sym_a}/{sym_b} spread z={current_z:.1f} "
            f"(half-life {hl:.0f}d, p={p['cointegration_pvalue']:.3f}). "
            f"{'Long ' + sym_b + ', short ' + sym_a if current_z > 0 else 'Long ' + sym_a + ', short ' + sym_b}."
        )

        signals.append({
            "date": today_str,
            "signal_type": "mean_reversion",
            "symbol_a": sym_a,
            "symbol_b": sym_b,
            "sector": p["sector"],
            "spread_zscore": round(current_z, 4),
            "correlation_60d": p["correlation_60d"],
            "cointegration_pvalue": p["cointegration_pvalue"],
            "hedge_ratio": p["hedge_ratio"],
            "half_life_days": p["half_life_days"],
            "pairs_score": round(raw_score, 1),
            "direction": direction,
            "runner_symbol": None,
            "runner_tech_score": None,
            "runner_fund_score": None,
            "narrative": narrative,
            "status": "active",
        })

    return signals


def _generate_runner_signals(
    pairs: list[dict],
    price_matrix: pd.DataFrame,
    tech_scores: dict[str, float],
    fund_scores: dict[str, float],
) -> list[dict]:
    """Detect runners: one leg diverging from pair with strong technicals + fundamentals."""
    signals = []
    today_str = date.today().isoformat()

    for p in pairs:
        sym_a, sym_b = p["symbol_a"], p["symbol_b"]
        hedge = p["hedge_ratio"]

        # Runner needs stronger correlation history (relationship was real)
        if p["correlation_60d"] < 0.70:
            continue

        if sym_a not in price_matrix.columns or sym_b not in price_matrix.columns:
            continue

        pa = price_matrix[sym_a].dropna()
        pb = price_matrix[sym_b].dropna()
        common = pa.index.intersection(pb.index)

        if len(common) < 60:
            continue

        pa_c = pa.loc[common]
        pb_c = pb.loc[common]

        log_spread = np.log(pa_c) - hedge * np.log(pb_c)
        rolling_mean = log_spread.rolling(60).mean()
        rolling_std = log_spread.rolling(60).std()
        zscore = (log_spread - rolling_mean) / rolling_std

        current_z = float(zscore.iloc[-1])

        if pd.isna(current_z) or abs(current_z) < PAIRS_ZSCORE_RUNNER_THRESHOLD:
            continue

        # Determine which leg is the outperformer (potential runner)
        if current_z > 0:
            runner, laggard = sym_a, sym_b  # A outperforming relative to B
        else:
            runner, laggard = sym_b, sym_a  # B outperforming relative to A

        # Check runner has strong technicals + fundamentals
        tech = tech_scores.get(runner, 0)
        fund = fund_scores.get(runner, 0)

        if tech < PAIRS_RUNNER_MIN_TECH or fund < PAIRS_RUNNER_MIN_FUND:
            continue

        # Score: weighted combination
        z_component = min(100, abs(current_z) * 25) * 0.30
        tech_component = tech * 0.30
        fund_component = fund * 0.20
        corr_component = (p["correlation_60d"] * 100) * 0.20
        runner_score = min(100, z_component + tech_component + fund_component + corr_component)

        direction = "long_a_short_b" if runner == sym_a else "long_b_short_a"

        narrative = (
            f"Runner: {runner} breaking away from {laggard} "
            f"(z={current_z:.1f}, corr={p['correlation_60d']:.2f}). "
            f"Tech={tech:.0f}, Fund={fund:.0f}. "
            f"Pair historically cointegrated (p={p['cointegration_pvalue']:.3f}) — "
            f"divergence suggests {runner} has a catalyst."
        )

        signals.append({
            "date": today_str,
            "signal_type": "runner",
            "symbol_a": sym_a,
            "symbol_b": sym_b,
            "sector": p["sector"],
            "spread_zscore": round(current_z, 4),
            "correlation_60d": p["correlation_60d"],
            "cointegration_pvalue": p["cointegration_pvalue"],
            "hedge_ratio": p["hedge_ratio"],
            "half_life_days": p["half_life_days"],
            "pairs_score": round(runner_score, 1),
            "direction": direction,
            "runner_symbol": runner,
            "runner_tech_score": round(tech, 1),
            "runner_fund_score": round(fund, 1),
            "narrative": narrative,
            "status": "active",
        })

    return signals


def _compute_pairs_scores(
    mr_signals: list[dict],
    runner_signals: list[dict],
) -> dict[str, float]:
    """Compute per-symbol pairs_score for convergence engine.

    Runner signals: use their pairs_score directly (40-100 range).
    Mean-reversion signals: small baseline for both legs (20-40 range).
    Per symbol, take the max across all signals.
    """
    scores: dict[str, float] = {}

    # Runner signals — only the runner symbol gets the full score
    for sig in runner_signals:
        sym = sig["runner_symbol"]
        if sym:
            scores[sym] = max(scores.get(sym, 0), sig["pairs_score"])

    # Mean-reversion signals — both legs get a baseline score
    for sig in mr_signals:
        baseline = min(40, sig["pairs_score"] * 0.4)
        for sym in [sig["symbol_a"], sig["symbol_b"]]:
            scores[sym] = max(scores.get(sym, 0), baseline)

    return scores


# ---------------------------------------------------------------------------
# Database writes
# ---------------------------------------------------------------------------

def _write_pair_relationships(pairs: list[dict]):
    """Write pair relationships to database."""
    if not pairs:
        return
    columns = [
        "symbol_a", "symbol_b", "sector", "correlation_60d", "correlation_120d",
        "cointegration_pvalue", "hedge_ratio", "half_life_days",
        "spread_mean", "spread_std", "last_updated",
    ]
    rows = [tuple(p[c] for c in columns) for p in pairs]
    upsert_many("pair_relationships", columns, rows)


def _write_spreads(spreads: list[dict]):
    """Write daily spreads to database."""
    if not spreads:
        return
    columns = ["symbol_a", "symbol_b", "date", "spread_raw", "spread_zscore", "spread_percentile"]
    rows = [tuple(s[c] for c in columns) for s in spreads]
    upsert_many("pair_spreads", columns, rows)


def _write_signals(signals: list[dict]):
    """Write pair signals to database (clear today's first to avoid duplicates)."""
    if not signals:
        return
    today_str = date.today().isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM pair_signals WHERE date = ?", [today_str])
        conn.executemany(
            """INSERT INTO pair_signals
               (date, signal_type, symbol_a, symbol_b, sector, spread_zscore,
                correlation_60d, cointegration_pvalue, hedge_ratio, half_life_days,
                pairs_score, direction, runner_symbol, runner_tech_score,
                runner_fund_score, narrative, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    s["date"], s["signal_type"], s["symbol_a"], s["symbol_b"],
                    s["sector"], s["spread_zscore"], s["correlation_60d"],
                    s["cointegration_pvalue"], s["hedge_ratio"], s["half_life_days"],
                    s["pairs_score"], s["direction"], s["runner_symbol"],
                    s["runner_tech_score"], s["runner_fund_score"],
                    s["narrative"], s["status"],
                )
                for s in signals
            ],
        )


def _load_existing_pairs() -> list[dict]:
    """Load cached pair relationships from database."""
    return query("""
        SELECT * FROM pair_relationships
        WHERE cointegration_pvalue <= ?
          AND half_life_days BETWEEN ? AND ?
        ORDER BY cointegration_pvalue ASC
    """, [PAIRS_COINT_PVALUE, PAIRS_HALF_LIFE_MIN, PAIRS_HALF_LIFE_MAX])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run():
    """Run pairs trading / statistical arbitrage analysis."""
    print("\n" + "=" * 60)
    print("  PAIRS TRADING / STAT ARB MODULE")
    print("=" * 60)

    from tools.db import init_db
    init_db()

    # 1. Load data
    print("  Loading sector groups...")
    sector_groups = _load_sector_groups()
    total_symbols = sum(len(v) for v in sector_groups.values())
    print(f"  {len(sector_groups)} sectors, {total_symbols} symbols")

    print("  Loading price matrix...")
    price_matrix = _load_price_matrix(min_days=PAIRS_MIN_PRICE_DAYS)
    if price_matrix.empty:
        print("  ✗ No price data available — skipping pairs analysis")
        return
    print(f"  Price matrix: {price_matrix.shape[0]} days × {price_matrix.shape[1]} symbols")

    # 2. Compute/refresh pair statistics (weekly)
    needs_refresh = _check_staleness()
    if needs_refresh:
        print("  Recomputing pair relationships (weekly refresh)...")
        pairs = _compute_pair_statistics(price_matrix, sector_groups)
        _write_pair_relationships(pairs)
    else:
        print("  Using cached pair relationships")
        pairs = _load_existing_pairs()

    if not pairs:
        print("  No cointegrated pairs found — skipping signal generation")
        print("=" * 60)
        return

    print(f"  Active cointegrated pairs: {len(pairs)}")

    # 3. Compute daily spreads
    print("  Computing daily spreads...")
    spreads = _compute_daily_spreads(pairs, price_matrix)
    _write_spreads(spreads)

    # 4. Generate signals
    print("  Generating mean-reversion signals...")
    mr_signals = _generate_mean_reversion_signals(pairs, price_matrix)

    print("  Generating runner signals...")
    tech_scores = _load_technical_scores()
    fund_scores = _load_fundamental_scores()
    runner_signals = _generate_runner_signals(pairs, price_matrix, tech_scores, fund_scores)

    # 5. Compute per-symbol scores for convergence
    symbol_scores = _compute_pairs_scores(mr_signals, runner_signals)

    # 6. Write all signals
    all_signals = mr_signals + runner_signals
    _write_signals(all_signals)

    # Summary
    print(f"\n  Mean-reversion signals: {len(mr_signals)}")
    print(f"  Runner signals:        {len(runner_signals)}")
    print(f"  Symbols with score:    {len(symbol_scores)}")
    if runner_signals:
        top = sorted(runner_signals, key=lambda s: s["pairs_score"], reverse=True)[:5]
        print("\n  Top runners:")
        for s in top:
            print(f"    {s['runner_symbol']:6s} score={s['pairs_score']:.0f}  "
                  f"z={s['spread_zscore']:.1f}  tech={s['runner_tech_score']:.0f}  "
                  f"fund={s['runner_fund_score']:.0f}  vs {s['symbol_a'] if s['runner_symbol'] == s['symbol_b'] else s['symbol_b']}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
