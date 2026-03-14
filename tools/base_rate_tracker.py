"""Base Rate Tracker — empirical signal outcome measurement.

Tracks every HIGH and NOTABLE convergence signal, then backfills
actual 30/60/90-day returns as time passes. Over time, reveals:

  1. Which conviction levels actually predict positive returns
  2. Which individual modules have the best hit rate
  3. Which module combinations co-occur too often (confirmation bias)
  4. Whether devil's advocate warnings correlate with losses

This is the empirical foundation for future weight adjustments.
Without this data, weight profiles are just educated guesses.

Usage:
  python -m tools.base_rate_tracker           # daily: log + update
  python -m tools.base_rate_tracker report    # generate performance report
"""

import json
import logging
import sys
from datetime import date, datetime

from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

# Module names matching convergence engine keys
ALL_MODULES = [
    "smartmoney", "worldview", "variant", "research",
    "news_displacement", "foreign_intel", "pairs",
    "main_signal", "alt_data", "sector_expert", "reddit",
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

    logged = 0
    with get_conn() as conn:
        for sig in signals:
            symbol = sig["symbol"]

            # Get entry price (latest close)
            price_rows = query(
                """
                SELECT close FROM price_data
                WHERE symbol = ? AND close IS NOT NULL
                ORDER BY date DESC LIMIT 1
                """,
                [symbol],
            )
            entry_price = price_rows[0]["close"] if price_rows else None

            if entry_price is None:
                continue

            # Get devil's advocate data if available
            da_rows = query(
                "SELECT risk_score, warning_flag FROM devils_advocate WHERE symbol = ? AND date = ?",
                [symbol, today],
            )
            da_risk = da_rows[0]["risk_score"] if da_rows else None
            da_warning = da_rows[0]["warning_flag"] if da_rows else 0

            # INSERT OR IGNORE — don't overwrite existing outcomes
            conn.execute(
                """
                INSERT OR IGNORE INTO signal_outcomes
                (symbol, signal_date, conviction_level, convergence_score,
                 module_count, active_modules, regime_at_signal, entry_price,
                 da_risk_score, da_warning)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol, today, sig["conviction_level"],
                    sig["convergence_score"], sig["module_count"],
                    sig["active_modules"], regime, entry_price,
                    da_risk, da_warning,
                ),
            )
            logged += 1

    print(f"  Logged {logged} new signals (entry prices captured)")
    return logged


# ── Update Outcomes ──────────────────────────────────────────────────

def update_outcomes():
    """Backfill 30/60/90-day returns for aged signals.

    Runs daily. For each signal that has passed its N-day mark but
    doesn't yet have the return filled in, fetch the price at N days
    and compute the return.
    """
    updated = {"30d": 0, "60d": 0, "90d": 0}

    # Define the windows to check
    windows = [
        ("return_30d", "price_30d", 30),
        ("return_60d", "price_60d", 60),
        ("return_90d", "price_90d", 90),
    ]

    for return_col, price_col, days in windows:
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
                updated[f"{days}d"] += 1

    # Check hit_target and hit_stop for signals with 90d returns
    _check_target_stop()

    total = sum(updated.values())
    if total:
        print(f"  Updated outcomes: 30d={updated['30d']}, 60d={updated['60d']}, 90d={updated['90d']}")
    else:
        print("  No outcomes to update (signals not yet aged)")

    return updated


def _check_target_stop():
    """Check if signals hit their target or stop loss within 90 days."""
    # Find signals that have 90d data but haven't been checked
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
            entry_price = row["entry_price"]

            # Get target and stop from signals table
            sig_rows = query(
                """
                SELECT target_price, stop_loss FROM signals
                WHERE symbol = ? AND date = ?
                """,
                [symbol, signal_date],
            )

            if not sig_rows:
                # No signal data — mark as unknown (0)
                conn.execute(
                    """
                    UPDATE signal_outcomes
                    SET hit_target = 0, hit_stop = 0
                    WHERE symbol = ? AND signal_date = ?
                    """,
                    [symbol, signal_date],
                )
                continue

            target = sig_rows[0]["target_price"]
            stop = sig_rows[0]["stop_loss"]

            # Check price range in the 90-day window
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

def generate_report():
    """Generate performance report across all resolved signals.

    Computes:
      - Win rate by conviction level
      - Average return by individual module
      - Module co-occurrence matrix (confirmation bias detection)
      - Best/worst module combinations
      - Devil's Advocate validation (did warnings correlate with losses?)
    """
    today = date.today().isoformat()

    print("\n" + "=" * 70)
    print("  BASE RATE PERFORMANCE REPORT")
    print("=" * 70)

    # Check data sufficiency
    total_resolved = query(
        "SELECT COUNT(*) as cnt FROM signal_outcomes WHERE return_30d IS NOT NULL"
    )
    n_resolved = total_resolved[0]["cnt"] if total_resolved else 0

    if n_resolved < 10:
        print(f"\n  Insufficient data: only {n_resolved} resolved signals (need 10+)")
        print("  Keep running the pipeline daily. Report will be meaningful after ~30 days.")
        print("=" * 70)
        return

    print(f"\n  Total resolved signals (30d+): {n_resolved}")

    # ── 1. Win Rate by Conviction Level ──
    print("\n  ── WIN RATE BY CONVICTION LEVEL ──")
    print(f"  {'Level':<12} {'Count':>6} {'Win%':>6} {'Avg 30d':>8} {'Avg 60d':>8} {'Avg 90d':>8}")
    print(f"  {'-'*54}")

    for level in ["HIGH", "NOTABLE"]:
        stats = query(
            """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN return_30d > 0 THEN 1 ELSE 0 END) as wins,
                   AVG(return_30d) as avg_30,
                   AVG(return_60d) as avg_60,
                   AVG(return_90d) as avg_90
            FROM signal_outcomes
            WHERE conviction_level = ? AND return_30d IS NOT NULL
            """,
            [level],
        )
        if stats and stats[0]["total"] > 0:
            s = stats[0]
            win_pct = (s["wins"] / s["total"]) * 100 if s["total"] else 0
            avg_30 = s["avg_30"] or 0
            avg_60 = s["avg_60"] or 0
            avg_90 = s["avg_90"] or 0
            print(f"  {level:<12} {s['total']:>6} {win_pct:>5.1f}% {avg_30:>+7.1f}% {avg_60:>+7.1f}% {avg_90:>+7.1f}%")

    # ── 2. Win Rate by Module ──
    print("\n  ── MODULE HIT RATES (when module was active) ──")
    print(f"  {'Module':<20} {'Signals':>8} {'Win%':>6} {'Avg 30d':>8}")
    print(f"  {'-'*46}")

    module_stats = []
    for module in ALL_MODULES:
        stats = query(
            """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN return_30d > 0 THEN 1 ELSE 0 END) as wins,
                   AVG(return_30d) as avg_30
            FROM signal_outcomes
            WHERE active_modules LIKE ?
              AND return_30d IS NOT NULL
            """,
            [f"%{module}%"],
        )
        if stats and stats[0]["total"] > 0:
            s = stats[0]
            win_pct = (s["wins"] / s["total"]) * 100
            avg_30 = s["avg_30"] or 0
            module_stats.append((module, s["total"], win_pct, avg_30))
            print(f"  {module:<20} {s['total']:>8} {win_pct:>5.1f}% {avg_30:>+7.1f}%")

            # Store in module_performance
            upsert_many(
                "module_performance",
                ["report_date", "module_name", "total_signals", "win_count",
                 "win_rate", "avg_return_30d", "avg_return_60d", "avg_return_90d"],
                [(today, module, s["total"], s["wins"], round(win_pct, 1),
                  round(avg_30, 2), 0, 0)],
            )

    # ── 3. Module Co-occurrence Matrix (confirmation bias detection) ──
    print("\n  ── MODULE CO-OCCURRENCE (confirmation bias check) ──")
    print("  Pairs with >80% co-occurrence may be double-counting the same signal:")

    high_cooccurrence = []
    for i, mod_a in enumerate(ALL_MODULES):
        for mod_b in ALL_MODULES[i + 1:]:
            stats = query(
                """
                SELECT
                    SUM(CASE WHEN active_modules LIKE ? AND active_modules LIKE ? THEN 1 ELSE 0 END) as both_active,
                    SUM(CASE WHEN active_modules LIKE ? THEN 1 ELSE 0 END) as a_active,
                    SUM(CASE WHEN active_modules LIKE ? THEN 1 ELSE 0 END) as b_active
                FROM signal_outcomes
                WHERE return_30d IS NOT NULL
                """,
                [f"%{mod_a}%", f"%{mod_b}%", f"%{mod_a}%", f"%{mod_b}%"],
            )
            if stats and stats[0]["a_active"] and stats[0]["b_active"]:
                s = stats[0]
                min_active = min(s["a_active"], s["b_active"])
                if min_active > 0:
                    cooccurrence = s["both_active"] / min_active
                    if cooccurrence > 0.80:
                        high_cooccurrence.append(
                            (mod_a, mod_b, cooccurrence, s["both_active"])
                        )

    if high_cooccurrence:
        high_cooccurrence.sort(key=lambda x: x[2], reverse=True)
        for mod_a, mod_b, rate, count in high_cooccurrence[:10]:
            print(f"    {mod_a} + {mod_b}: {rate:.0%} co-occurrence ({count} signals)")
        print("  --> Consider reducing combined weight of highly correlated modules")
    else:
        print("    No high co-occurrence pairs detected (good — modules are independent)")

    # ── 4. Devil's Advocate Validation ──
    da_signals = query(
        """
        SELECT COUNT(*) as total,
               SUM(CASE WHEN da_warning = 1 THEN 1 ELSE 0 END) as warned,
               AVG(CASE WHEN da_warning = 1 THEN return_30d END) as warned_avg,
               AVG(CASE WHEN da_warning = 0 OR da_warning IS NULL THEN return_30d END) as clean_avg
        FROM signal_outcomes
        WHERE return_30d IS NOT NULL AND da_risk_score IS NOT NULL
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
            print(f"  Avg 30d return (warned): {warned_avg:+.1f}%")
            print(f"  Avg 30d return (clean):  {clean_avg:+.1f}%")
            if warned_avg < clean_avg:
                print("  --> DA warnings correlate with worse returns (DA is adding value)")
            else:
                print("  --> DA warnings NOT correlating with losses (consider recalibrating)")

    # ── 5. Best/Worst Module Combos ──
    print(f"\n  ── BEST & WORST MODULE COMBINATIONS ──")
    combos = query(
        """
        SELECT active_modules, COUNT(*) as cnt, AVG(return_30d) as avg_ret
        FROM signal_outcomes
        WHERE return_30d IS NOT NULL
        GROUP BY active_modules
        HAVING cnt >= 2
        ORDER BY avg_ret DESC
        """
    )
    if combos:
        print(f"  {'Modules':<50} {'N':>4} {'Avg 30d':>8}")
        print(f"  {'-'*64}")
        # Top 3 best
        for c in combos[:3]:
            modules = json.loads(c["active_modules"]) if c["active_modules"] else []
            mod_str = "+".join(m[:8] for m in modules)[:48]
            print(f"  {mod_str:<50} {c['cnt']:>4} {c['avg_ret']:>+7.1f}%")
        if len(combos) > 6:
            print(f"  {'...':^64}")
        # Bottom 3 worst
        for c in combos[-3:]:
            modules = json.loads(c["active_modules"]) if c["active_modules"] else []
            mod_str = "+".join(m[:8] for m in modules)[:48]
            print(f"  {mod_str:<50} {c['cnt']:>4} {c['avg_ret']:>+7.1f}%")

    print("\n" + "=" * 70)


# ── Import DA_WARNING_THRESHOLD for report ────────────────────────────
from tools.config import DA_WARNING_THRESHOLD


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
