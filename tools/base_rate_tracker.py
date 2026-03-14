"""Base Rate Tracker — empirical signal outcome measurement.

Tracks every HIGH and NOTABLE convergence signal, then backfills
actual 1/5/10/20/30/60/90-day returns as time passes. Over time, reveals:

  1. Which conviction levels actually predict positive returns
  2. Which individual modules have the best hit rate
  3. Which module combinations co-occur too often (confirmation bias)
  4. Whether devil's advocate warnings correlate with losses
  5. Module performance by regime and sector (for adaptive weight optimization)

This is the empirical foundation for adaptive weight adjustments.
Without this data, weight profiles are just educated guesses.

Usage:
  python -m tools.base_rate_tracker           # daily: log + update
  python -m tools.base_rate_tracker report    # generate performance report
"""

import json
import logging
import math
import sys
from datetime import date, datetime

from tools.db import init_db, get_conn, query, upsert_many
from tools.config import DA_WARNING_THRESHOLD

logger = logging.getLogger(__name__)

# Module names matching convergence engine keys (all 18)
ALL_MODULES = [
    "smartmoney", "worldview", "variant", "research",
    "news_displacement", "foreign_intel", "pairs",
    "main_signal", "alt_data", "sector_expert", "reddit",
    "ma", "energy_intel", "prediction_markets", "pattern_options",
    "estimate_momentum", "ai_regulatory", "consensus_blindspots",
]

# All return windows to track
RETURN_WINDOWS = [
    ("return_1d",  "price_1d",  1),
    ("return_5d",  "price_5d",  5),
    ("return_10d", "price_10d", 10),
    ("return_20d", "price_20d", 20),
    ("return_30d", "price_30d", 30),
    ("return_60d", "price_60d", 60),
    ("return_90d", "price_90d", 90),
]


# ── Log New Signals ──────────────────────────────────────────────────

def log_signals():
    """Log today's HIGH/NOTABLE convergence signals with entry prices.

    Uses INSERT OR IGNORE to avoid overwriting signals that already
    have outcome data filled in from previous runs.
    """
    today = date.today().isoformat()

    # Get today's HIGH and NOTABLE signals
    signals = query(
        """
        SELECT symbol, convergence_score, module_count, conviction_level,
               active_modules, narrative
        FROM convergence_signals
        WHERE date = ? AND conviction_level IN ('HIGH', 'NOTABLE')
        """,
        [today],
    )

    if not signals:
        print("  No HIGH/NOTABLE signals to log today")
        return 0

    # Get current regime
    regime_rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime = regime_rows[0]["regime"] if regime_rows else "neutral"

    # Batch-fetch all supporting data in 3 queries instead of N+1
    symbols = [s["symbol"] for s in signals]
    placeholders = ",".join("?" * len(symbols))

    # Latest close prices (one query)
    price_map = {}
    price_rows = query(
        f"""SELECT p.symbol, p.close FROM price_data p
            INNER JOIN (SELECT symbol, MAX(date) as mx FROM price_data
                        WHERE symbol IN ({placeholders}) AND close IS NOT NULL
                        GROUP BY symbol) m
            ON p.symbol = m.symbol AND p.date = m.mx""",
        symbols,
    )
    for r in price_rows:
        price_map[r["symbol"]] = r["close"]

    # Sector + market cap (one query via JOIN)
    meta_map = {}
    meta_rows = query(
        f"""SELECT su.symbol, su.sector, f.value as marketCap
            FROM stock_universe su
            LEFT JOIN fundamentals f ON f.symbol = su.symbol AND f.metric = 'marketCap'
            WHERE su.symbol IN ({placeholders})""",
        symbols,
    )
    for r in meta_rows:
        mcap = r["marketCap"]
        cap_bucket = (
            "mega" if mcap and mcap > 200e9 else
            "large" if mcap and mcap > 10e9 else
            "mid" if mcap and mcap > 2e9 else
            "small" if mcap else None
        )
        meta_map[r["symbol"]] = (r["sector"], cap_bucket)

    # Devil's advocate data (one query)
    da_map = {}
    da_rows = query(
        f"""SELECT symbol, risk_score, warning_flag FROM devils_advocate
            WHERE date = ? AND symbol IN ({placeholders})""",
        [today] + symbols,
    )
    for r in da_rows:
        da_map[r["symbol"]] = (r["risk_score"], r["warning_flag"])

    logged = 0
    with get_conn() as conn:
        for sig in signals:
            symbol = sig["symbol"]
            entry_price = price_map.get(symbol)
            if entry_price is None:
                continue

            sector, cap_bucket = meta_map.get(symbol, (None, None))
            da_risk, da_warning = da_map.get(symbol, (None, 0))

            conn.execute(
                """
                INSERT OR IGNORE INTO signal_outcomes
                (symbol, signal_date, conviction_level, convergence_score,
                 module_count, active_modules, regime_at_signal,
                 sector, market_cap_bucket, entry_price,
                 da_risk_score, da_warning)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol, today, sig["conviction_level"],
                    sig["convergence_score"], sig["module_count"],
                    sig["active_modules"], regime,
                    sector, cap_bucket, entry_price,
                    da_risk, da_warning,
                ),
            )
            logged += 1

    print(f"  Logged {logged} new signals (entry prices captured)")
    return logged


# ── Update Outcomes ──────────────────────────────────────────────────

def update_outcomes():
    """Backfill 1/5/10/20/30/60/90-day returns for aged signals.

    Runs daily. For each signal that has passed its N-day mark but
    doesn't yet have the return filled in, fetch the price at N days
    and compute the return.
    """
    updated = {}

    for return_col, price_col, days in RETURN_WINDOWS:
        label = f"{days}d"
        updated[label] = 0

        # Find signals that are old enough but don't have this return yet
        stale = query(
            f"""
            SELECT symbol, signal_date, entry_price
            FROM signal_outcomes
            WHERE {return_col} IS NULL
              AND entry_price IS NOT NULL
              AND signal_date <= date('now', '-{days} days')
            """,
        )

        if not stale:
            continue

        with get_conn() as conn:
            for row in stale:
                symbol = row["symbol"]
                signal_date = row["signal_date"]
                entry_price = row["entry_price"]

                # Get close price at +N days (nearest available trading day)
                price_rows = query(
                    """
                    SELECT close FROM price_data
                    WHERE symbol = ?
                      AND date >= date(?, ?)
                      AND close IS NOT NULL
                    ORDER BY date ASC
                    LIMIT 1
                    """,
                    [symbol, signal_date, f"+{days} days"],
                )

                if not price_rows or price_rows[0]["close"] is None:
                    continue

                future_price = price_rows[0]["close"]
                pct_return = round(
                    (future_price - entry_price) / entry_price * 100, 2
                )

                conn.execute(
                    f"""
                    UPDATE signal_outcomes
                    SET {price_col} = ?, {return_col} = ?
                    WHERE symbol = ? AND signal_date = ?
                    """,
                    [future_price, pct_return, symbol, signal_date],
                )
                updated[label] += 1

    # Check hit_target and hit_stop for signals with 90d returns
    _check_target_stop()

    total = sum(updated.values())
    if total:
        parts = ", ".join(f"{k}={v}" for k, v in updated.items() if v > 0)
        print(f"  Updated outcomes: {parts}")
    else:
        print("  No outcomes to update (signals not yet aged)")

    return updated


def _check_target_stop():
    """Check if signals hit their target or stop loss within 90 days."""
    unchecked = query(
        """
        SELECT so.symbol, so.signal_date, so.entry_price
        FROM signal_outcomes so
        WHERE so.return_90d IS NOT NULL
          AND so.hit_target IS NULL
        """,
    )

    if not unchecked:
        return

    with get_conn() as conn:
        for row in unchecked:
            symbol = row["symbol"]
            signal_date = row["signal_date"]

            # Get target and stop from signals table
            sig_rows = query(
                """
                SELECT target_price, stop_loss FROM signals
                WHERE symbol = ? AND date = ?
                """,
                [symbol, signal_date],
            )

            if not sig_rows:
                conn.execute(
                    """
                    UPDATE signal_outcomes
                    SET hit_target = 0, hit_stop = 0
                    WHERE symbol = ? AND signal_date = ?
                    """,
                    [symbol, signal_date],
                )
                continue

            target = sig_rows[0].get("target_price")
            stop = sig_rows[0].get("stop_loss")

            extremes = query(
                """
                SELECT MAX(high) as max_high, MIN(low) as min_low
                FROM price_data
                WHERE symbol = ?
                  AND date > ?
                  AND date <= date(?, '+90 days')
                """,
                [symbol, signal_date, signal_date],
            )

            hit_target = 0
            hit_stop = 0

            if extremes and extremes[0]["max_high"] is not None:
                if target and extremes[0]["max_high"] >= target:
                    hit_target = 1
                if stop and extremes[0]["min_low"] <= stop:
                    hit_stop = 1

            conn.execute(
                """
                UPDATE signal_outcomes
                SET hit_target = ?, hit_stop = ?
                WHERE symbol = ? AND signal_date = ?
                """,
                [hit_target, hit_stop, symbol, signal_date],
            )


# ── Performance Report ────────────────────────────────────────────────

def _compute_sharpe(returns: list[float]) -> float | None:
    """Compute Sharpe ratio from a list of returns."""
    if len(returns) < 5:
        return None
    avg = sum(returns) / len(returns)
    variance = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance) if variance > 0 else 0
    if std == 0:
        return None
    return round(avg / std, 2)


def _confidence_interval_95(returns: list[float]) -> tuple[float, float] | None:
    """95% confidence interval for mean return."""
    n = len(returns)
    if n < 5:
        return None
    avg = sum(returns) / n
    variance = sum((r - avg) ** 2 for r in returns) / (n - 1)
    std_err = math.sqrt(variance / n)
    margin = 1.96 * std_err
    return (round(avg - margin, 2), round(avg + margin, 2))


def generate_report():
    """Generate performance report across all resolved signals.

    Computes:
      - Win rate by conviction level (all holding periods)
      - Module hit rates (overall, by regime, by sector)
      - Module co-occurrence matrix (confirmation bias detection)
      - Best/worst module combinations
      - Devil's Advocate validation
      - Sharpe ratios and confidence intervals
    """
    today = date.today().isoformat()

    print("\n" + "=" * 70)
    print("  BASE RATE PERFORMANCE REPORT")
    print("=" * 70)

    # Check data sufficiency — use shortest window that has data
    for check_col in ["return_5d", "return_10d", "return_20d", "return_30d"]:
        total_resolved = query(
            f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE {check_col} IS NOT NULL"
        )
        n_resolved = total_resolved[0]["cnt"] if total_resolved else 0
        if n_resolved >= 10:
            break

    if n_resolved < 10:
        print(f"\n  Insufficient data: only {n_resolved} resolved signals (need 10+)")
        print("  Keep running the pipeline daily. Report will be meaningful after ~5 days.")
        print("=" * 70)
        return

    # Count resolved by window
    for _, _, days in RETURN_WINDOWS:
        cnt = query(
            f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE return_{days}d IS NOT NULL"
        )
        n = cnt[0]["cnt"] if cnt else 0
        if n > 0:
            print(f"  Resolved signals ({days}d): {n}")

    # ── 1. Win Rate by Conviction Level (all holding periods) ──
    print("\n  ── WIN RATE BY CONVICTION LEVEL ──")
    header_periods = ["1d", "5d", "10d", "20d", "30d"]
    print(f"  {'Level':<10} {'N':>5} " + " ".join(f"{'Win'+p:>7}" for p in header_periods))
    print(f"  {'-'*60}")

    for level in ["HIGH", "NOTABLE"]:
        # Use the shortest available window for total count
        base_stats = query(
            """
            SELECT COUNT(*) as total
            FROM signal_outcomes
            WHERE conviction_level = ?
              AND (return_5d IS NOT NULL OR return_30d IS NOT NULL)
            """,
            [level],
        )
        total = base_stats[0]["total"] if base_stats else 0
        if total == 0:
            continue

        win_pcts = []
        for period in header_periods:
            stats = query(
                f"""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN return_{period} > 0 THEN 1 ELSE 0 END) as wins
                FROM signal_outcomes
                WHERE conviction_level = ? AND return_{period} IS NOT NULL
                """,
                [level],
            )
            if stats and stats[0]["total"] > 0:
                win_pcts.append(f"{(stats[0]['wins'] / stats[0]['total']) * 100:>6.1f}%")
            else:
                win_pcts.append(f"{'--':>7}")

        print(f"  {level:<10} {total:>5} " + " ".join(win_pcts))

    # ── 2. Module Hit Rates (overall) ──
    print("\n  ── MODULE HIT RATES (when module was active) ──")
    # Use the best available return window
    best_return_col = "return_30d"
    for col in ["return_20d", "return_10d", "return_5d"]:
        cnt = query(f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE {col} IS NOT NULL")
        if cnt and cnt[0]["cnt"] >= 10:
            best_return_col = col
            break

    best_period = best_return_col.replace("return_", "")
    print(f"  {'Module':<22} {'N':>6} {'Win%':>6} {'Avg':>7} {'Sharpe':>7} {'CI_low':>7} {'CI_hi':>7}")
    print(f"  {'-'*68}")

    module_stats = []
    for module in ALL_MODULES:
        stats = query(
            f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN {best_return_col} > 0 THEN 1 ELSE 0 END) as wins,
                   AVG({best_return_col}) as avg_ret
            FROM signal_outcomes
            WHERE active_modules LIKE ?
              AND {best_return_col} IS NOT NULL
            """,
            [f'%"{module}"%'],
        )
        if not stats or stats[0]["total"] == 0:
            continue

        s = stats[0]
        win_pct = (s["wins"] / s["total"]) * 100
        avg_ret = s["avg_ret"] or 0

        # Get individual returns for Sharpe and CI
        returns_rows = query(
            f"""
            SELECT {best_return_col} as ret
            FROM signal_outcomes
            WHERE active_modules LIKE ?
              AND {best_return_col} IS NOT NULL
            """,
            [f'%"{module}"%'],
        )
        returns = [r["ret"] for r in returns_rows if r["ret"] is not None]
        sharpe = _compute_sharpe(returns)
        ci = _confidence_interval_95(returns)

        sharpe_str = f"{sharpe:>7.2f}" if sharpe is not None else f"{'--':>7}"
        ci_low_str = f"{ci[0]:>+6.1f}%" if ci else f"{'--':>7}"
        ci_hi_str = f"{ci[1]:>+6.1f}%" if ci else f"{'--':>7}"

        print(f"  {module:<22} {s['total']:>6} {win_pct:>5.1f}% {avg_ret:>+6.1f}% {sharpe_str} {ci_low_str} {ci_hi_str}")

        module_stats.append((module, s["total"], win_pct, avg_ret, sharpe))

        # Store in module_performance (overall)
        # Get avg returns for all periods
        period_avgs = {}
        for _, _, days in RETURN_WINDOWS:
            pavg = query(
                f"SELECT AVG(return_{days}d) as avg FROM signal_outcomes WHERE active_modules LIKE ? AND return_{days}d IS NOT NULL",
                [f'%"{module}"%'],
            )
            period_avgs[f"avg_return_{days}d"] = round(pavg[0]["avg"], 2) if pavg and pavg[0]["avg"] else None

        upsert_many(
            "module_performance",
            ["report_date", "module_name", "regime", "sector",
             "total_signals", "win_count", "win_rate",
             "avg_return_1d", "avg_return_5d", "avg_return_10d",
             "avg_return_20d", "avg_return_30d", "avg_return_60d", "avg_return_90d",
             "sharpe_ratio", "observation_count",
             "confidence_interval_low", "confidence_interval_high"],
            [(today, module, "all", "all",
              s["total"], s["wins"], round(win_pct, 1),
              period_avgs.get("avg_return_1d"), period_avgs.get("avg_return_5d"),
              period_avgs.get("avg_return_10d"), period_avgs.get("avg_return_20d"),
              period_avgs.get("avg_return_30d"), period_avgs.get("avg_return_60d"),
              period_avgs.get("avg_return_90d"),
              sharpe, s["total"],
              ci[0] if ci else None, ci[1] if ci else None)],
        )

    # ── 2b. Module Hit Rates by Regime ──
    regimes_in_data = query(
        "SELECT DISTINCT regime_at_signal FROM signal_outcomes WHERE regime_at_signal IS NOT NULL"
    )
    regime_list = [r["regime_at_signal"] for r in regimes_in_data] if regimes_in_data else []

    if regime_list:
        print(f"\n  ── MODULE PERFORMANCE BY REGIME ({best_period}) ──")
        for regime in sorted(regime_list):
            regime_count = query(
                f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE regime_at_signal = ? AND {best_return_col} IS NOT NULL",
                [regime],
            )
            rc = regime_count[0]["cnt"] if regime_count else 0
            if rc < 5:
                continue

            print(f"\n  Regime: {regime} ({rc} signals)")
            for module in ALL_MODULES:
                stats = query(
                    f"""
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN {best_return_col} > 0 THEN 1 ELSE 0 END) as wins,
                           AVG({best_return_col}) as avg_ret
                    FROM signal_outcomes
                    WHERE active_modules LIKE ?
                      AND regime_at_signal = ?
                      AND {best_return_col} IS NOT NULL
                    """,
                    [f'%"{module}"%', regime],
                )
                if not stats or stats[0]["total"] < 3:
                    continue
                s = stats[0]
                win_pct = (s["wins"] / s["total"]) * 100
                avg_ret = s["avg_ret"] or 0

                # Get returns for Sharpe
                ret_rows = query(
                    f"""SELECT {best_return_col} as ret FROM signal_outcomes
                    WHERE active_modules LIKE ? AND regime_at_signal = ? AND {best_return_col} IS NOT NULL""",
                    [f'%"{module}"%', regime],
                )
                rets = [r["ret"] for r in ret_rows if r["ret"] is not None]
                sharpe = _compute_sharpe(rets)

                print(f"    {module:<22} {s['total']:>4} {win_pct:>5.1f}% {avg_ret:>+6.1f}%"
                      + (f" Sharpe={sharpe:.2f}" if sharpe else ""))

                # Store regime-specific performance
                # Get avg returns for all periods under this regime
                regime_period_avgs = {}
                for _, _, rdays in RETURN_WINDOWS:
                    rpavg = query(
                        f"SELECT AVG(return_{rdays}d) as avg FROM signal_outcomes WHERE active_modules LIKE ? AND regime_at_signal = ? AND return_{rdays}d IS NOT NULL",
                        [f'%"{module}"%', regime],
                    )
                    regime_period_avgs[f"avg_return_{rdays}d"] = round(rpavg[0]["avg"], 2) if rpavg and rpavg[0]["avg"] else None

                upsert_many(
                    "module_performance",
                    ["report_date", "module_name", "regime", "sector",
                     "total_signals", "win_count", "win_rate",
                     "avg_return_1d", "avg_return_5d", "avg_return_10d",
                     "avg_return_20d", "avg_return_30d", "avg_return_60d", "avg_return_90d",
                     "sharpe_ratio", "observation_count"],
                    [(today, module, regime, "all",
                      s["total"], s["wins"], round(win_pct, 1),
                      regime_period_avgs.get("avg_return_1d"), regime_period_avgs.get("avg_return_5d"),
                      regime_period_avgs.get("avg_return_10d"), regime_period_avgs.get("avg_return_20d"),
                      regime_period_avgs.get("avg_return_30d"), regime_period_avgs.get("avg_return_60d"),
                      regime_period_avgs.get("avg_return_90d"),
                      sharpe, s["total"])],
                )

    # ── 3. Module Co-occurrence Matrix (confirmation bias detection) ──
    print("\n  ── MODULE CO-OCCURRENCE (confirmation bias check) ──")
    print("  Pairs with >80% co-occurrence may be double-counting the same signal:")

    # Compute co-occurrence in Python from a single DB fetch (not 153 queries)
    all_active = query(
        f"SELECT active_modules FROM signal_outcomes WHERE {best_return_col} IS NOT NULL"
    )
    module_counts = {m: 0 for m in ALL_MODULES}
    pair_counts: dict[tuple[str, str], int] = {}
    for row in all_active:
        try:
            mods = json.loads(row["active_modules"]) if row["active_modules"] else []
        except (json.JSONDecodeError, TypeError):
            continue
        mod_set = set(mods) & set(ALL_MODULES)
        for m in mod_set:
            module_counts[m] += 1
        mod_list = sorted(mod_set)
        for i_idx, ma in enumerate(mod_list):
            for mb in mod_list[i_idx + 1:]:
                pair_counts[(ma, mb)] = pair_counts.get((ma, mb), 0) + 1

    high_cooccurrence = []
    for (mod_a, mod_b), both in pair_counts.items():
        min_active = min(module_counts.get(mod_a, 0), module_counts.get(mod_b, 0))
        if min_active > 0:
            cooccurrence = both / min_active
            if cooccurrence > 0.80:
                high_cooccurrence.append((mod_a, mod_b, cooccurrence, both))

    if high_cooccurrence:
        high_cooccurrence.sort(key=lambda x: x[2], reverse=True)
        for mod_a, mod_b, rate, count in high_cooccurrence[:10]:
            print(f"    {mod_a} + {mod_b}: {rate:.0%} co-occurrence ({count} signals)")
        print("  --> Consider reducing combined weight of highly correlated modules")
    else:
        print("    No high co-occurrence pairs detected (good — modules are independent)")

    # ── 4. Devil's Advocate Validation ──
    da_signals = query(
        f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN da_warning = 1 THEN 1 ELSE 0 END) as warned,
               AVG(CASE WHEN da_warning = 1 THEN {best_return_col} END) as warned_avg,
               AVG(CASE WHEN da_warning = 0 OR da_warning IS NULL THEN {best_return_col} END) as clean_avg
        FROM signal_outcomes
        WHERE {best_return_col} IS NOT NULL AND da_risk_score IS NOT NULL
        """
    )
    if da_signals and da_signals[0]["total"] > 0:
        s = da_signals[0]
        print(f"\n  ── DEVIL'S ADVOCATE VALIDATION ──")
        print(f"  Signals with DA analysis: {s['total']}")
        print(f"  Warned (risk>{DA_WARNING_THRESHOLD}): {s['warned'] or 0}")
        warned_avg = s["warned_avg"]
        clean_avg = s["clean_avg"]
        if warned_avg is not None and clean_avg is not None:
            print(f"  Avg {best_period} return (warned): {warned_avg:+.1f}%")
            print(f"  Avg {best_period} return (clean):  {clean_avg:+.1f}%")
            if warned_avg < clean_avg:
                print("  --> DA warnings correlate with worse returns (DA is adding value)")
            else:
                print("  --> DA warnings NOT correlating with losses (consider recalibrating)")

    # ── 5. Best/Worst Module Combos ──
    print(f"\n  ── BEST & WORST MODULE COMBINATIONS ({best_period}) ──")
    combos = query(
        f"""
        SELECT active_modules, COUNT(*) as cnt, AVG({best_return_col}) as avg_ret
        FROM signal_outcomes
        WHERE {best_return_col} IS NOT NULL
        GROUP BY active_modules
        HAVING cnt >= 2
        ORDER BY avg_ret DESC
        """
    )
    if combos:
        print(f"  {'Modules':<50} {'N':>4} {'Avg':>8}")
        print(f"  {'-'*64}")
        for c in combos[:3]:
            modules = json.loads(c["active_modules"]) if c["active_modules"] else []
            mod_str = "+".join(m[:8] for m in modules)[:48]
            print(f"  {mod_str:<50} {c['cnt']:>4} {c['avg_ret']:>+7.1f}%")
        if len(combos) > 6:
            print(f"  {'...':^64}")
        for c in combos[-3:]:
            modules = json.loads(c["active_modules"]) if c["active_modules"] else []
            mod_str = "+".join(m[:8] for m in modules)[:48]
            print(f"  {mod_str:<50} {c['cnt']:>4} {c['avg_ret']:>+7.1f}%")

    print("\n" + "=" * 70)


# ── Entry Point ───────────────────────────────────────────────────────

def run():
    """Daily run: log new signals, update aged outcomes."""
    init_db()

    print("\n" + "=" * 60)
    print("  BASE RATE TRACKER")
    print("=" * 60)

    log_signals()
    update_outcomes()

    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()

    if len(sys.argv) > 1 and sys.argv[1] == "report":
        generate_report()
    else:
        run()
