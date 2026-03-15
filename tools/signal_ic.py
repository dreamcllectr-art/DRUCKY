"""Signal Information Coefficient (IC) Backtester — Druckenmiller Alpha System.

Computes Spearman IC for each module's scores vs. forward returns across multiple
horizons (1d / 5d / 10d / 20d / 30d / 60d / 90d).  Also slices by macro regime
to show which modules work best in risk_on vs risk_off environments.

Tables written:
  signal_ic_results    (per module × date × horizon IC value)
  module_ic_summary    (aggregate IC stats per module × regime × horizon)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from tools.db import get_conn, query, query_df, upsert_many

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HORIZONS: list[int] = [1, 5, 10, 20, 30, 60, 90]  # trading days

# All modules that produce a per-symbol score we can IC against returns
# Maps module_name → SQL to pull (symbol, date, score)
MODULE_SCORE_QUERIES: dict[str, str] = {
    "technical": """
        SELECT symbol, date, total_score AS score
        FROM technical_scores
        WHERE total_score IS NOT NULL
    """,
    "fundamental": """
        SELECT symbol, date, total_score AS score
        FROM fundamental_scores
        WHERE total_score IS NOT NULL
    """,
    "convergence": """
        SELECT symbol, date, convergence_score AS score
        FROM convergence_signals
        WHERE convergence_score IS NOT NULL
    """,
    "smart_money": """
        SELECT symbol, date, conviction_score AS score
        FROM smart_money_scores
        WHERE conviction_score IS NOT NULL
    """,
    "news_sentiment": """
        SELECT symbol, date, AVG(sentiment) AS score
        FROM news_sentiment
        GROUP BY symbol, date
    """,
    "estimate_momentum": """
        SELECT symbol, date, score
        FROM alt_data_scores
        WHERE source = 'estimate_momentum'
          AND score IS NOT NULL
    """,
    "alternative_data": """
        SELECT symbol, date, AVG(score) AS score
        FROM alt_data_scores
        WHERE source != 'estimate_momentum'
        GROUP BY symbol, date
    """,
    "pairs": """
        SELECT symbol, date, score
        FROM alt_data_scores
        WHERE source = 'pairs'
          AND score IS NOT NULL
    """,
    "foreign_intel": """
        SELECT symbol, date, score
        FROM foreign_intel_signals
        WHERE score IS NOT NULL
    """,
    "cross_asset": """
        SELECT symbol, date, opportunity_score AS score
        FROM cross_asset_opportunities
        WHERE opportunity_score IS NOT NULL
          AND asset_class NOT IN ('commodity_energy','commodity_gold',
                                   'commodity_grain','commodity_copper','crypto')
    """,
}

REGIMES: list[str] = [
    "all", "strong_risk_on", "risk_on", "neutral", "risk_off", "strong_risk_off"
]

MIN_OBSERVATIONS: int = 10   # minimum cross-sectional size to compute IC
MIN_IC_DATES: int = 5        # minimum dates for rolling IC summary
BOOTSTRAP_N: int = 500       # bootstrap iterations for confidence intervals


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_prices() -> pd.DataFrame:
    """Return price_data as DataFrame indexed by (symbol, date)."""
    df = query_df(
        "SELECT symbol, date, adj_close FROM price_data WHERE adj_close IS NOT NULL ORDER BY date"
    )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index(["symbol", "date"]).sort_index()
    return df


def _load_macro_regimes() -> pd.Series:
    """Return Series: date → regime string."""
    rows = query(
        "SELECT date, regime FROM macro_scores WHERE regime IS NOT NULL ORDER BY date"
    )
    if not rows:
        return pd.Series(dtype=str)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["regime"]


def _load_module_scores(module: str, sql: str) -> pd.DataFrame:
    """Return DataFrame with columns [symbol, date, score]."""
    try:
        df = query_df(sql)
        if df.empty:
            return pd.DataFrame(columns=["symbol", "date", "score"])
        df["date"] = pd.to_datetime(df["date"])
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        return df.dropna(subset=["score"])
    except Exception as e:
        logger.warning("Could not load scores for %s: %s", module, e)
        return pd.DataFrame(columns=["symbol", "date", "score"])


# ---------------------------------------------------------------------------
# Forward return computation
# ---------------------------------------------------------------------------

def _compute_forward_returns(
    prices: pd.DataFrame, horizons: list[int]
) -> dict[int, pd.DataFrame]:
    """
    For each horizon h, compute forward return = price[t+h] / price[t] - 1.
    Returns dict: horizon → DataFrame with columns [symbol, date, fwd_return].
    """
    result: dict[int, pd.DataFrame] = {}

    # Pivot to symbol × date matrix
    if prices.empty:
        return {h: pd.DataFrame(columns=["symbol", "date", "fwd_return"]) for h in horizons}

    try:
        price_matrix = prices["adj_close"].unstack(level="symbol")  # date × symbol
    except Exception:
        return {h: pd.DataFrame(columns=["symbol", "date", "fwd_return"]) for h in horizons}

    for h in horizons:
        fwd = price_matrix.shift(-h) / price_matrix - 1
        fwd_long = (
            fwd.stack()
            .reset_index()
            .rename(columns={"level_0": "date", 0: "fwd_return"})
        )
        fwd_long = fwd_long.dropna(subset=["fwd_return"])
        result[h] = fwd_long

    return result


# ---------------------------------------------------------------------------
# IC computation
# ---------------------------------------------------------------------------

def _spearman_ic(scores: pd.Series, returns: pd.Series) -> float:
    """Spearman rank correlation between scores and returns. Returns NaN if insufficient data."""
    mask = scores.notna() & returns.notna()
    if mask.sum() < MIN_OBSERVATIONS:
        return float("nan")
    r, _ = stats.spearmanr(scores[mask], returns[mask])
    return float(r)


def _compute_ic_series(
    scores_df: pd.DataFrame,
    fwd_returns: dict[int, pd.DataFrame],
) -> dict[int, pd.DataFrame]:
    """
    For each horizon, compute daily IC by joining scores × forward returns on (symbol, date).
    Returns dict: horizon → DataFrame[date, ic, n_stocks].
    """
    result: dict[int, pd.DataFrame] = {}

    for h, fwd_df in fwd_returns.items():
        if fwd_df.empty:
            result[h] = pd.DataFrame(columns=["date", "ic", "n_stocks"])
            continue

        merged = scores_df.merge(fwd_df, on=["symbol", "date"], how="inner")
        if merged.empty:
            result[h] = pd.DataFrame(columns=["date", "ic", "n_stocks"])
            continue

        records = []
        for dt, grp in merged.groupby("date"):
            ic = _spearman_ic(grp["score"], grp["fwd_return"])
            if not np.isnan(ic):
                records.append({"date": dt, "ic": ic, "n_stocks": len(grp)})

        result[h] = pd.DataFrame(records) if records else pd.DataFrame(
            columns=["date", "ic", "n_stocks"]
        )

    return result


# ---------------------------------------------------------------------------
# Bootstrap confidence intervals
# ---------------------------------------------------------------------------

def _bootstrap_ci(
    ic_series: pd.Series, n: int = BOOTSTRAP_N, alpha: float = 0.05
) -> tuple[float, float]:
    """Return (low, high) confidence interval via bootstrap."""
    if len(ic_series) < MIN_IC_DATES:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(42)
    boot_means = [
        ic_series.iloc[rng.integers(0, len(ic_series), len(ic_series))].mean()
        for _ in range(n)
    ]
    low = float(np.percentile(boot_means, 100 * alpha / 2))
    high = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return low, high


# ---------------------------------------------------------------------------
# Summary stats
# ---------------------------------------------------------------------------

def _ic_stats(
    ic_series: pd.Series,
    n_stocks_series: pd.Series,
) -> dict:
    if len(ic_series) < MIN_IC_DATES:
        return {}
    ci_low, ci_high = _bootstrap_ci(ic_series)
    mean_ic = float(ic_series.mean())
    std_ic = float(ic_series.std())
    ir = mean_ic / std_ic if std_ic > 0 else float("nan")
    # t-test: IC > 0?
    _, pval = stats.ttest_1samp(ic_series.dropna(), 0)
    return {
        "mean_ic": round(mean_ic, 4),
        "std_ic": round(std_ic, 4),
        "ir": round(ir, 4) if not np.isnan(ir) else None,
        "ic_positive_pct": round((ic_series > 0).mean(), 3),
        "n_dates": len(ic_series),
        "avg_n_stocks": round(float(n_stocks_series.mean()), 1),
        "ci_low": round(ci_low, 4) if not np.isnan(ci_low) else None,
        "ci_high": round(ci_high, 4) if not np.isnan(ci_high) else None,
        "is_significant": bool(pval < 0.05) if not np.isnan(pval) else False,
        "pvalue": round(float(pval), 4) if not np.isnan(pval) else None,
    }


# ---------------------------------------------------------------------------
# Fallback: reconstruct signals from technical_scores + prices
# ---------------------------------------------------------------------------

def _reconstruct_signals_from_technicals(
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """
    When signal_outcomes is empty, reconstruct synthetic signals from
    technical_scores (HIGH conviction: total_score >= 70).
    Returns DataFrame[symbol, date, convergence_score, module_count, regime_at_signal].
    """
    rows = query("""
        SELECT ts.symbol, ts.date, ts.total_score AS convergence_score,
               3 AS module_count,
               COALESCE(ms.regime, 'neutral') AS regime_at_signal
        FROM technical_scores ts
        LEFT JOIN macro_scores ms ON ms.date = ts.date
        WHERE ts.total_score >= 60
        ORDER BY ts.date
    """)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Main run()
# ---------------------------------------------------------------------------

def run() -> None:
    """Compute IC for all modules and write results to DB."""
    today_str = date.today().isoformat()
    logger.info("signal_ic: starting IC computation for %s", today_str)

    _ensure_tables()

    # Load shared data
    prices = _load_prices()
    if prices.empty:
        logger.warning("signal_ic: no price data — aborting")
        return

    macro_regimes = _load_macro_regimes()
    fwd_returns = _compute_forward_returns(prices, HORIZONS)

    ic_result_rows: list[tuple] = []   # for signal_ic_results
    summary_rows: list[tuple] = []      # for module_ic_summary

    for module, sql in MODULE_SCORE_QUERIES.items():
        logger.info("signal_ic: computing IC for module=%s", module)
        scores_df = _load_module_scores(module, sql)

        if scores_df.empty:
            logger.info("signal_ic: no data for %s — skipping", module)
            continue

        # Per-horizon daily IC
        ic_series_by_horizon = _compute_ic_series(scores_df, fwd_returns)

        # Store raw IC results per date
        for h, ic_df in ic_series_by_horizon.items():
            if ic_df.empty:
                continue
            for _, row in ic_df.iterrows():
                dt = row["date"]
                regime = "unknown"
                if not macro_regimes.empty:
                    # Find closest regime at or before this date
                    past = macro_regimes[macro_regimes.index <= dt]
                    if not past.empty:
                        regime = past.iloc[-1]
                ic_result_rows.append((
                    module,
                    dt.date().isoformat(),
                    today_str,
                    h,
                    round(float(row["ic"]), 4),
                    int(row["n_stocks"]),
                    regime,
                ))

        # Summary stats per module × regime × horizon
        for regime_filter in REGIMES:
            for h, ic_df in ic_series_by_horizon.items():
                if ic_df.empty:
                    continue

                # Filter by regime if not 'all'
                if regime_filter != "all" and not macro_regimes.empty:
                    ic_df = ic_df.copy()
                    ic_df["regime"] = ic_df["date"].map(
                        lambda d: macro_regimes.get(d, None)
                    )
                    ic_df = ic_df[ic_df["regime"] == regime_filter]

                if len(ic_df) < MIN_IC_DATES:
                    continue

                stats_dict = _ic_stats(ic_df["ic"], ic_df["n_stocks"])
                if not stats_dict:
                    continue

                summary_rows.append((
                    module,
                    regime_filter,
                    h,
                    today_str,
                    stats_dict["mean_ic"],
                    stats_dict["std_ic"],
                    stats_dict.get("ir"),
                    stats_dict["ic_positive_pct"],
                    stats_dict["n_dates"],
                    stats_dict["avg_n_stocks"],
                    stats_dict.get("ci_low"),
                    stats_dict.get("ci_high"),
                    stats_dict["is_significant"],
                    stats_dict.get("pvalue"),
                    json.dumps({"module": module, "regime": regime_filter, "horizon": h}),
                ))

    # Write IC results
    if ic_result_rows:
        upsert_many(
            "signal_ic_results",
            ["module", "signal_date", "computed_date", "horizon_days",
             "ic_value", "n_stocks", "regime"],
            ic_result_rows,
        )
        logger.info("signal_ic: wrote %d IC result rows", len(ic_result_rows))

    if summary_rows:
        upsert_many(
            "module_ic_summary",
            ["module", "regime", "horizon_days", "computed_date",
             "mean_ic", "std_ic", "information_ratio", "ic_positive_pct",
             "n_dates", "avg_n_stocks", "ci_low", "ci_high",
             "is_significant", "pvalue", "details"],
            summary_rows,
        )
        logger.info("signal_ic: wrote %d summary rows", len(summary_rows))

    # Also compute module ranking for the latest date
    _write_module_ranking(today_str)

    logger.info("signal_ic: complete")


def _write_module_ranking(report_date: str) -> None:
    """Write a ranked view of modules by IC quality into module_ic_summary."""
    rows = query("""
        SELECT module, AVG(mean_ic) AS avg_ic, AVG(information_ratio) AS avg_ir,
               AVG(is_significant) AS sig_rate, AVG(n_dates) AS avg_dates
        FROM module_ic_summary
        WHERE regime = 'all' AND horizon_days IN (5, 10, 20)
        GROUP BY module
        ORDER BY avg_ic DESC
    """)
    if rows:
        logger.info("signal_ic: module IC ranking (5/10/20d, all regimes):")
        for r in rows:
            logger.info(
                "  %-25s  IC=%.3f  IR=%.2f  sig=%.0f%%  n=%d dates",
                r["module"],
                r["avg_ic"] or 0,
                r["avg_ir"] or 0,
                (r["sig_rate"] or 0) * 100,
                int(r["avg_dates"] or 0),
            )


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

def _ensure_tables() -> None:
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signal_ic_results (
            module          TEXT NOT NULL,
            signal_date     TEXT NOT NULL,
            computed_date   TEXT NOT NULL,
            horizon_days    INTEGER NOT NULL,
            ic_value        REAL,
            n_stocks        INTEGER,
            regime          TEXT,
            PRIMARY KEY (module, signal_date, horizon_days)
        );

        CREATE TABLE IF NOT EXISTS module_ic_summary (
            module              TEXT NOT NULL,
            regime              TEXT NOT NULL,
            horizon_days        INTEGER NOT NULL,
            computed_date       TEXT NOT NULL,
            mean_ic             REAL,
            std_ic              REAL,
            information_ratio   REAL,
            ic_positive_pct     REAL,
            n_dates             INTEGER,
            avg_n_stocks        REAL,
            ci_low              REAL,
            ci_high             REAL,
            is_significant      INTEGER DEFAULT 0,
            pvalue              REAL,
            details             TEXT,
            PRIMARY KEY (module, regime, horizon_days)
        );
    """)
    conn.commit()
    conn.close()


# Run table creation on import
try:
    _ensure_tables()
except Exception as _e:
    logger.warning("Could not ensure signal_ic tables: %s", _e)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    run()
