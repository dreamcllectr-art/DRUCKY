"""Pairs Trading / Statistical Arbitrage Module — mean-reversion + runner detection."""
import logging, math
from datetime import date, datetime
from itertools import combinations
import numpy as np, pandas as pd
from statsmodels.tsa.stattools import coint
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from tools.db import get_conn, query, query_df, upsert_many
from tools.config import (
    PAIRS_MIN_CORRELATION, PAIRS_COINT_PVALUE, PAIRS_HALF_LIFE_MIN, PAIRS_HALF_LIFE_MAX,
    PAIRS_ZSCORE_MR_THRESHOLD, PAIRS_ZSCORE_RUNNER_THRESHOLD, PAIRS_RUNNER_MIN_TECH,
    PAIRS_RUNNER_MIN_FUND, PAIRS_LOOKBACK_DAYS, PAIRS_REFRESH_DAYS, PAIRS_MIN_PRICE_DAYS,
)
logger = logging.getLogger(__name__)


def _load_sector_groups() -> dict[str, list[str]]:
    rows = query("SELECT symbol, sector FROM stock_universe WHERE sector IS NOT NULL AND sector != ''")
    groups: dict[str, list[str]] = {}
    for r in rows:
        groups.setdefault(r["sector"], []).append(r["symbol"])
    return groups


def _load_price_matrix(min_days: int = 120) -> pd.DataFrame:
    df = query_df("SELECT symbol, date, close FROM price_data WHERE close IS NOT NULL ORDER BY date")
    if df.empty:
        return pd.DataFrame()
    pivot = df.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5)
    valid_cols = pivot.columns[pivot.count() >= min_days]
    pivot = pivot[valid_cols]
    return pivot.dropna(axis=1, thresh=int(len(pivot) * 0.9))


def _load_scores(table, col) -> dict[str, float]:
    rows = query(f"SELECT t.symbol, t.{col} FROM {table} t INNER JOIN (SELECT symbol, MAX(date) as mx FROM {table} GROUP BY symbol) m ON t.symbol = m.symbol AND t.date = m.mx WHERE t.{col} IS NOT NULL")
    return {r["symbol"]: r[col] for r in rows}


def _compute_hedge_ratio(pa: pd.Series, pb: pd.Series) -> float:
    log_a, log_b = np.log(pa.dropna()), np.log(pb.dropna())
    common = log_a.index.intersection(log_b.index)
    if len(common) < 30:
        return float("nan")
    return float(OLS(log_a.loc[common].values, add_constant(log_b.loc[common].values)).fit().params[1])


def _compute_half_life(spread: pd.Series) -> float:
    spread = spread.dropna()
    if len(spread) < 30:
        return float("nan")
    lag = spread.shift(1)
    delta = spread - lag
    valid = ~(lag.isna() | delta.isna())
    if valid.sum() < 20:
        return float("nan")
    phi = OLS(delta[valid].values, add_constant(lag[valid].values)).fit().params[1]
    if phi >= 0:
        return float("nan")
    return float(-math.log(2) / math.log(1 + phi))


def _check_staleness() -> bool:
    rows = query("SELECT MAX(last_updated) as latest FROM pair_relationships")
    if not rows or rows[0]["latest"] is None:
        return True
    try:
        return (date.today() - datetime.strptime(rows[0]["latest"], "%Y-%m-%d").date()).days >= PAIRS_REFRESH_DAYS
    except (ValueError, TypeError):
        return True


def _compute_pair_statistics(price_matrix: pd.DataFrame, sector_groups: dict[str, list[str]]) -> list[dict]:
    results, available, today_str = [], set(price_matrix.columns), date.today().isoformat()
    total_tested = total_coint = 0
    for sector, symbols in sector_groups.items():
        syms = sorted([s for s in symbols if s in available])
        if len(syms) < 2:
            continue
        pm = price_matrix[syms].iloc[-PAIRS_LOOKBACK_DAYS:]
        if len(pm) < PAIRS_MIN_PRICE_DAYS:
            continue
        for sym_a, sym_b in combinations(syms, 2):
            if sym_a > sym_b:
                sym_a, sym_b = sym_b, sym_a
            pa, pb = pm[sym_a].dropna(), pm[sym_b].dropna()
            common = pa.index.intersection(pb.index)
            if len(common) < PAIRS_MIN_PRICE_DAYS:
                continue
            pa_c, pb_c = pa.loc[common], pb.loc[common]
            corr_60 = pa_c.iloc[-60:].corr(pb_c.iloc[-60:]) if len(common) >= 60 else float("nan")
            corr_120 = pa_c.iloc[-120:].corr(pb_c.iloc[-120:]) if len(common) >= 120 else float("nan")
            if math.isnan(corr_60) or corr_60 < PAIRS_MIN_CORRELATION:
                continue
            total_tested += 1
            try:
                _, pvalue, _ = coint(pa_c.values, pb_c.values)
            except Exception:
                continue
            if pvalue > PAIRS_COINT_PVALUE:
                continue
            hedge = _compute_hedge_ratio(pa_c, pb_c)
            if math.isnan(hedge):
                continue
            log_spread = np.log(pa_c) - hedge * np.log(pb_c)
            half_life = _compute_half_life(log_spread)
            if math.isnan(half_life) or half_life < PAIRS_HALF_LIFE_MIN or half_life > PAIRS_HALF_LIFE_MAX:
                continue
            total_coint += 1
            results.append({"symbol_a": sym_a, "symbol_b": sym_b, "sector": sector,
                "correlation_60d": round(corr_60, 4), "correlation_120d": round(corr_120, 4) if not math.isnan(corr_120) else None,
                "cointegration_pvalue": round(pvalue, 6), "hedge_ratio": round(hedge, 4),
                "half_life_days": round(half_life, 1), "spread_mean": round(float(log_spread.mean()), 6),
                "spread_std": round(float(log_spread.std()), 6), "last_updated": today_str})
    print(f"  Tested {total_tested} pairs, found {total_coint} cointegrated")
    return results


def _get_spread_zscore(price_matrix, sym_a, sym_b, hedge):
    """Get log spread and rolling z-score for a pair. Returns (log_spread, zscore) or (None, None)."""
    if sym_a not in price_matrix.columns or sym_b not in price_matrix.columns:
        return None, None
    pa, pb = price_matrix[sym_a].dropna(), price_matrix[sym_b].dropna()
    common = pa.index.intersection(pb.index)
    if len(common) < 60:
        return None, None
    pa_c, pb_c = pa.loc[common], pb.loc[common]
    log_spread = np.log(pa_c) - hedge * np.log(pb_c)
    rm, rs = log_spread.rolling(60).mean(), log_spread.rolling(60).std()
    return log_spread, (log_spread - rm) / rs


def _compute_daily_spreads(pairs: list[dict], price_matrix: pd.DataFrame) -> list[dict]:
    results = []
    for p in pairs:
        log_spread, zscore = _get_spread_zscore(price_matrix, p["symbol_a"], p["symbol_b"], p["hedge_ratio"])
        if log_spread is None:
            continue
        current_spread = float(log_spread.iloc[-1])
        spread_percentile = float((log_spread < current_spread).mean() * 100)
        for dt, z in zscore.iloc[-5:].items():
            if pd.isna(z):
                continue
            dt_str = str(dt)[:10] if not isinstance(dt, str) else dt
            results.append({"symbol_a": p["symbol_a"], "symbol_b": p["symbol_b"], "date": dt_str,
                "spread_raw": round(float(log_spread.loc[dt]), 6), "spread_zscore": round(float(z), 4),
                "spread_percentile": round(spread_percentile, 1)})
    return results


def _generate_mean_reversion_signals(pairs: list[dict], price_matrix: pd.DataFrame) -> list[dict]:
    signals, today_str = [], date.today().isoformat()
    for p in pairs:
        _, zscore = _get_spread_zscore(price_matrix, p["symbol_a"], p["symbol_b"], p["hedge_ratio"])
        if zscore is None:
            continue
        current_z = float(zscore.iloc[-1])
        if pd.isna(current_z) or abs(current_z) < PAIRS_ZSCORE_MR_THRESHOLD:
            continue
        raw_score = min(100, abs(current_z) * 25)
        if p["half_life_days"] < 30:
            raw_score = min(100, raw_score * 1.2)
        direction = "long_b_short_a" if current_z > 0 else "long_a_short_b"
        sym_a, sym_b, hl = p["symbol_a"], p["symbol_b"], p["half_life_days"]
        long_sym = sym_b if current_z > 0 else sym_a
        short_sym = sym_a if current_z > 0 else sym_b
        signals.append({"date": today_str, "signal_type": "mean_reversion", "symbol_a": sym_a, "symbol_b": sym_b,
            "sector": p["sector"], "spread_zscore": round(current_z, 4), "correlation_60d": p["correlation_60d"],
            "cointegration_pvalue": p["cointegration_pvalue"], "hedge_ratio": p["hedge_ratio"],
            "half_life_days": hl, "pairs_score": round(raw_score, 1), "direction": direction,
            "runner_symbol": None, "runner_tech_score": None, "runner_fund_score": None,
            "narrative": f"Mean-reversion: {sym_a}/{sym_b} z={current_z:.1f} (hl {hl:.0f}d, p={p['cointegration_pvalue']:.3f}). Long {long_sym}, short {short_sym}.",
            "status": "active"})
    return signals


def _generate_runner_signals(pairs: list[dict], price_matrix: pd.DataFrame, tech_scores: dict, fund_scores: dict) -> list[dict]:
    signals, today_str = [], date.today().isoformat()
    for p in pairs:
        if p["correlation_60d"] < 0.70:
            continue
        _, zscore = _get_spread_zscore(price_matrix, p["symbol_a"], p["symbol_b"], p["hedge_ratio"])
        if zscore is None:
            continue
        current_z = float(zscore.iloc[-1])
        if pd.isna(current_z) or abs(current_z) < PAIRS_ZSCORE_RUNNER_THRESHOLD:
            continue
        runner = p["symbol_a"] if current_z > 0 else p["symbol_b"]
        laggard = p["symbol_b"] if current_z > 0 else p["symbol_a"]
        tech, fund = tech_scores.get(runner, 0), fund_scores.get(runner, 0)
        if tech < PAIRS_RUNNER_MIN_TECH or fund < PAIRS_RUNNER_MIN_FUND:
            continue
        runner_score = min(100, min(100, abs(current_z) * 25) * 0.30 + tech * 0.30 + fund * 0.20 + (p["correlation_60d"] * 100) * 0.20)
        direction = "long_a_short_b" if runner == p["symbol_a"] else "long_b_short_a"
        signals.append({"date": today_str, "signal_type": "runner", "symbol_a": p["symbol_a"], "symbol_b": p["symbol_b"],
            "sector": p["sector"], "spread_zscore": round(current_z, 4), "correlation_60d": p["correlation_60d"],
            "cointegration_pvalue": p["cointegration_pvalue"], "hedge_ratio": p["hedge_ratio"],
            "half_life_days": p["half_life_days"], "pairs_score": round(runner_score, 1), "direction": direction,
            "runner_symbol": runner, "runner_tech_score": round(tech, 1), "runner_fund_score": round(fund, 1),
            "narrative": f"Runner: {runner} breaking from {laggard} (z={current_z:.1f}, corr={p['correlation_60d']:.2f}). Tech={tech:.0f}, Fund={fund:.0f}. Cointegrated (p={p['cointegration_pvalue']:.3f}).",
            "status": "active"})
    return signals


def _write_pair_relationships(pairs: list[dict]):
    if not pairs:
        return
    cols = ["symbol_a", "symbol_b", "sector", "correlation_60d", "correlation_120d", "cointegration_pvalue", "hedge_ratio", "half_life_days", "spread_mean", "spread_std", "last_updated"]
    upsert_many("pair_relationships", cols, [tuple(p[c] for c in cols) for p in pairs])


def _write_spreads(spreads: list[dict]):
    if not spreads:
        return
    cols = ["symbol_a", "symbol_b", "date", "spread_raw", "spread_zscore", "spread_percentile"]
    upsert_many("pair_spreads", cols, [tuple(s[c] for c in cols) for s in spreads])


def _write_signals(signals: list[dict]):
    if not signals:
        return
    today_str = date.today().isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM pair_signals WHERE date = ?", [today_str])
        conn.executemany(
            """INSERT INTO pair_signals (date, signal_type, symbol_a, symbol_b, sector, spread_zscore,
                correlation_60d, cointegration_pvalue, hedge_ratio, half_life_days, pairs_score, direction,
                runner_symbol, runner_tech_score, runner_fund_score, narrative, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(s["date"], s["signal_type"], s["symbol_a"], s["symbol_b"], s["sector"], s["spread_zscore"],
              s["correlation_60d"], s["cointegration_pvalue"], s["hedge_ratio"], s["half_life_days"],
              s["pairs_score"], s["direction"], s["runner_symbol"], s["runner_tech_score"],
              s["runner_fund_score"], s["narrative"], s["status"]) for s in signals])


def run():
    """Run pairs trading / statistical arbitrage analysis."""
    print("\n" + "=" * 60 + "\n  PAIRS TRADING / STAT ARB MODULE\n" + "=" * 60)
    from tools.db import init_db
    init_db()
    print("  Loading sector groups...")
    sector_groups = _load_sector_groups()
    print(f"  {len(sector_groups)} sectors, {sum(len(v) for v in sector_groups.values())} symbols")
    print("  Loading price matrix...")
    price_matrix = _load_price_matrix(min_days=PAIRS_MIN_PRICE_DAYS)
    if price_matrix.empty:
        print("  No price data — skipping"); return
    print(f"  Price matrix: {price_matrix.shape[0]} days x {price_matrix.shape[1]} symbols")
    if _check_staleness():
        print("  Recomputing pair relationships (weekly refresh)...")
        pairs = _compute_pair_statistics(price_matrix, sector_groups)
        _write_pair_relationships(pairs)
    else:
        print("  Using cached pair relationships")
        pairs = query(f"SELECT * FROM pair_relationships WHERE cointegration_pvalue <= {PAIRS_COINT_PVALUE} AND half_life_days BETWEEN {PAIRS_HALF_LIFE_MIN} AND {PAIRS_HALF_LIFE_MAX} ORDER BY cointegration_pvalue ASC")
    if not pairs:
        print("  No cointegrated pairs found"); print("=" * 60); return
    print(f"  Active cointegrated pairs: {len(pairs)}")
    print("  Computing daily spreads...")
    _write_spreads(_compute_daily_spreads(pairs, price_matrix))
    print("  Generating signals...")
    mr_signals = _generate_mean_reversion_signals(pairs, price_matrix)
    tech_scores = _load_scores("technical_scores", "total_score")
    fund_scores = _load_scores("fundamental_scores", "total_score")
    runner_signals = _generate_runner_signals(pairs, price_matrix, tech_scores, fund_scores)
    _write_signals(mr_signals + runner_signals)
    print(f"\n  Mean-reversion: {len(mr_signals)} | Runners: {len(runner_signals)}")
    if runner_signals:
        print("\n  Top runners:")
        for s in sorted(runner_signals, key=lambda s: s["pairs_score"], reverse=True)[:5]:
            vs = s["symbol_a"] if s["runner_symbol"] == s["symbol_b"] else s["symbol_b"]
            print(f"    {s['runner_symbol']:6s} score={s['pairs_score']:.0f} z={s['spread_zscore']:.1f} tech={s['runner_tech_score']:.0f} fund={s['runner_fund_score']:.0f} vs {vs}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
