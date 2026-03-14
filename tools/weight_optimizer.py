"""Adaptive Weight Optimizer — the data moat flywheel.

Reads empirical module performance from base_rate_tracker outcomes,
computes Bayesian-updated weights, and writes them to weight_history
for the convergence engine to consume.

The longer this system runs, the better it gets. A competitor who copies
the code on day 1 is equally good on day 1000 — but they can't copy
the 6+ months of accumulated outcome data that calibrates these weights.

Pipeline phase: 3.55 (after base_rate_tracker, before memos)

Usage:
  python -m tools.weight_optimizer           # daily: compute + store
  python -m tools.weight_optimizer status    # show current state
"""

import json
import logging
import math
from datetime import date, datetime

from tools.db import init_db, get_conn, query, upsert_many
from tools.config import (
    CONVERGENCE_WEIGHTS,
    REGIME_CONVERGENCE_WEIGHTS,
    WO_MIN_WEIGHT,
    WO_MAX_WEIGHT,
    WO_MIN_OBSERVATIONS,
    WO_MAX_DELTA_PER_CYCLE,
    WO_LEARNING_RATE,
    WO_MIN_TOTAL_SIGNALS,
    WO_MIN_DAYS_RUNNING,
    WO_ENABLE_ADAPTIVE,
    WO_HOLDOUT_MODULES,
)

logger = logging.getLogger(__name__)


def _check_data_sufficiency() -> dict:
    """Check if we have enough data to start optimizing.

    Returns dict with:
      - sufficient: bool
      - total_resolved: int
      - days_running: int
      - modules_with_data: int
      - reason: str (if insufficient)
    """
    # Total resolved signals (any window)
    total = query(
        """SELECT COUNT(*) as cnt FROM signal_outcomes
           WHERE return_5d IS NOT NULL OR return_10d IS NOT NULL
                 OR return_20d IS NOT NULL OR return_30d IS NOT NULL"""
    )
    total_resolved = total[0]["cnt"] if total else 0

    # Days running
    first_signal = query(
        "SELECT MIN(signal_date) as first_date FROM signal_outcomes"
    )
    if first_signal and first_signal[0]["first_date"]:
        first_date = datetime.strptime(first_signal[0]["first_date"], "%Y-%m-%d").date()
        days_running = (date.today() - first_date).days
    else:
        days_running = 0

    # Count modules with sufficient observations
    modules_ok = 0
    for module in CONVERGENCE_WEIGHTS:
        if module in WO_HOLDOUT_MODULES:
            continue
        cnt = query(
            """SELECT COUNT(*) as cnt FROM signal_outcomes
               WHERE active_modules LIKE ? AND return_5d IS NOT NULL""",
            [f'%"{module}"%'],
        )
        if cnt and cnt[0]["cnt"] >= WO_MIN_OBSERVATIONS:
            modules_ok += 1

    result = {
        "total_resolved": total_resolved,
        "days_running": days_running,
        "modules_with_data": modules_ok,
        "sufficient": True,
        "reason": None,
    }

    if total_resolved < WO_MIN_TOTAL_SIGNALS:
        result["sufficient"] = False
        result["reason"] = (
            f"Need {WO_MIN_TOTAL_SIGNALS} resolved signals, have {total_resolved}"
        )
    elif days_running < WO_MIN_DAYS_RUNNING:
        result["sufficient"] = False
        result["reason"] = (
            f"Need {WO_MIN_DAYS_RUNNING} days of data, have {days_running}"
        )
    elif modules_ok < 5:
        result["sufficient"] = False
        result["reason"] = (
            f"Need 5+ modules with {WO_MIN_OBSERVATIONS}+ observations, have {modules_ok}"
        )

    return result


def _get_module_performance(regime: str = "all") -> dict[str, dict]:
    """Get empirical performance for each module.

    Returns: {module_name: {win_rate, avg_return, sharpe, n_observations}}
    """
    # Use best available return window
    best_col = "return_30d"
    for col in ["return_20d", "return_10d", "return_5d"]:
        cnt = query(f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE {col} IS NOT NULL")
        if cnt and cnt[0]["cnt"] >= 20:
            best_col = col
            break

    results = {}
    for module in CONVERGENCE_WEIGHTS:
        if module in WO_HOLDOUT_MODULES:
            continue

        regime_filter = ""
        params = [f'%"{module}"%']
        if regime != "all":
            regime_filter = "AND regime_at_signal = ?"
            params.append(regime)

        stats = query(
            f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN {best_col} > 0 THEN 1 ELSE 0 END) as wins,
                   AVG({best_col}) as avg_ret
            FROM signal_outcomes
            WHERE active_modules LIKE ?
              AND {best_col} IS NOT NULL
              {regime_filter}
            """,
            params,
        )

        if not stats or stats[0]["total"] < 5:
            continue

        s = stats[0]
        win_rate = (s["wins"] / s["total"]) * 100 if s["total"] else 0
        avg_ret = s["avg_ret"] or 0

        # Compute Sharpe ratio
        ret_rows = query(
            f"""SELECT {best_col} as ret FROM signal_outcomes
                WHERE active_modules LIKE ? AND {best_col} IS NOT NULL {regime_filter}""",
            params,
        )
        returns = [r["ret"] for r in ret_rows if r["ret"] is not None]
        sharpe = None
        if len(returns) >= 5:
            avg = sum(returns) / len(returns)
            var = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
            std = math.sqrt(var) if var > 0 else 0
            if std > 0:
                sharpe = avg / std

        results[module] = {
            "win_rate": win_rate,
            "avg_return": avg_ret,
            "sharpe": sharpe,
            "n_observations": s["total"],
        }

    return results


def _compute_optimal_weights(
    prior_weights: dict[str, float],
    performance: dict[str, dict],
    regime: str,
) -> dict[str, float]:
    """Bayesian weight update: adjust priors based on empirical Sharpe ratios.

    Formula: posterior = prior * (1 + alpha * (sharpe_i - median_sharpe))
    Then clamp to [MIN, MAX], enforce max delta, renormalize to 1.0.
    """
    alpha = WO_LEARNING_RATE

    # Get Sharpe values for modules with sufficient data
    sharpes = {}
    for module, perf in performance.items():
        if perf["sharpe"] is not None and perf["n_observations"] >= WO_MIN_OBSERVATIONS:
            sharpes[module] = perf["sharpe"]

    if len(sharpes) < 5:
        return prior_weights  # Not enough modules with Sharpe data

    # Median Sharpe as reference
    sorted_sharpes = sorted(sharpes.values())
    mid = len(sorted_sharpes) // 2
    median_sharpe = (
        sorted_sharpes[mid]
        if len(sorted_sharpes) % 2
        else (sorted_sharpes[mid - 1] + sorted_sharpes[mid]) / 2
    )

    # Compute posterior weights
    new_weights = {}
    for module, prior in prior_weights.items():
        if module in WO_HOLDOUT_MODULES:
            new_weights[module] = prior
            continue

        if module in sharpes:
            adjustment = alpha * (sharpes[module] - median_sharpe)
            posterior = prior * (1 + adjustment)
        else:
            # No data yet — keep prior
            posterior = prior

        # Clamp to bounds
        posterior = max(WO_MIN_WEIGHT, min(WO_MAX_WEIGHT, posterior))

        # Enforce max delta per cycle
        delta = posterior - prior
        if abs(delta) > WO_MAX_DELTA_PER_CYCLE:
            posterior = prior + (WO_MAX_DELTA_PER_CYCLE if delta > 0 else -WO_MAX_DELTA_PER_CYCLE)

        new_weights[module] = posterior

    # Renormalize to sum to 1.0
    total = sum(new_weights.values())
    if total > 0:
        new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

    return new_weights


def _get_prior_weights(regime: str) -> dict[str, float]:
    """Get the most recent weights for this regime from history, or fall back to static."""
    # Check weight_history for latest adaptive weights
    rows = query(
        """SELECT module_name, weight FROM weight_history
           WHERE regime = ?
             AND date = (SELECT MAX(date) FROM weight_history WHERE regime = ?)""",
        [regime, regime],
    )
    if rows and len(rows) >= 10:
        return {r["module_name"]: r["weight"] for r in rows}

    # Fall back to static config
    return REGIME_CONVERGENCE_WEIGHTS.get(regime, dict(CONVERGENCE_WEIGHTS))


def optimize_weights():
    """Main optimization: compute optimal weights for each regime profile.

    Returns dict of changes made, or None if insufficient data.
    """
    today = date.today().isoformat()

    # Data sufficiency check
    sufficiency = _check_data_sufficiency()
    if not sufficiency["sufficient"]:
        print(f"  Data insufficient: {sufficiency['reason']}")
        print(f"    Resolved signals: {sufficiency['total_resolved']}")
        print(f"    Days running: {sufficiency['days_running']}")
        print(f"    Modules with {WO_MIN_OBSERVATIONS}+ obs: {sufficiency['modules_with_data']}")

        # Log the insufficiency
        upsert_many(
            "weight_optimizer_log",
            ["date", "action", "details"],
            [(today, "skip_insufficient_data", json.dumps(sufficiency))],
        )
        return None

    # Optimize for each regime profile
    regimes = list(REGIME_CONVERGENCE_WEIGHTS.keys()) + ["all"]
    all_changes = {}

    for regime in regimes:
        # Get empirical performance for this regime
        performance = _get_module_performance(regime)

        if len(performance) < 5:
            continue

        # Get prior weights (from history or static config)
        if regime == "all":
            prior = dict(CONVERGENCE_WEIGHTS)
        else:
            prior = _get_prior_weights(regime)

        # Compute optimal weights
        optimal = _compute_optimal_weights(prior, performance, regime)

        # Calculate changes
        changes = []
        for module in optimal:
            prior_w = prior.get(module, 0)
            new_w = optimal[module]
            delta = new_w - prior_w
            if abs(delta) >= 0.001:  # Only log meaningful changes
                changes.append({
                    "module": module,
                    "prior": prior_w,
                    "new": new_w,
                    "delta": delta,
                    "sharpe": performance.get(module, {}).get("sharpe"),
                    "n_obs": performance.get(module, {}).get("n_observations", 0),
                })

        # Write to weight_history
        rows = []
        for module, weight in optimal.items():
            prior_w = prior.get(module, 0)
            delta = weight - prior_w
            reason_parts = []
            perf = performance.get(module, {})
            if perf.get("sharpe") is not None:
                reason_parts.append(f"sharpe={perf['sharpe']:.3f}")
            if perf.get("n_observations"):
                reason_parts.append(f"n={perf['n_observations']}")
            if abs(delta) >= 0.001:
                reason_parts.append(f"delta={delta:+.4f}")
            reason = ", ".join(reason_parts) if reason_parts else "no change"

            rows.append((today, regime, module, round(weight, 4), round(prior_w, 4), reason))

        if rows:
            upsert_many(
                "weight_history",
                ["date", "regime", "module_name", "weight", "prior_weight", "reason"],
                rows,
            )

        if changes:
            all_changes[regime] = changes

    # Log the optimization run
    summary = {
        "regimes_optimized": len(all_changes),
        "total_changes": sum(len(c) for c in all_changes.values()),
        "sufficiency": sufficiency,
    }
    upsert_many(
        "weight_optimizer_log",
        ["date", "action", "details"],
        [(today, "optimize_complete", json.dumps(summary))],
    )

    return all_changes


def print_status():
    """Print current optimizer state and weight evolution."""
    print("\n" + "=" * 70)
    print("  ADAPTIVE WEIGHT OPTIMIZER — STATUS")
    print("=" * 70)

    # Data sufficiency
    sufficiency = _check_data_sufficiency()
    print(f"\n  Data Sufficiency: {'YES' if sufficiency['sufficient'] else 'NO'}")
    print(f"    Total resolved signals: {sufficiency['total_resolved']} (need {WO_MIN_TOTAL_SIGNALS})")
    print(f"    Days running: {sufficiency['days_running']} (need {WO_MIN_DAYS_RUNNING})")
    print(f"    Modules with {WO_MIN_OBSERVATIONS}+ obs: {sufficiency['modules_with_data']}")
    if not sufficiency["sufficient"]:
        print(f"    Reason: {sufficiency['reason']}")

    # Latest weights vs static
    latest = query(
        """SELECT module_name, weight, prior_weight, reason
           FROM weight_history
           WHERE regime = 'all'
             AND date = (SELECT MAX(date) FROM weight_history WHERE regime = 'all')
           ORDER BY weight DESC"""
    )
    if latest:
        print(f"\n  ── LATEST ADAPTIVE WEIGHTS (vs static) ──")
        print(f"  {'Module':<22} {'Static':>7} {'Adaptive':>9} {'Delta':>7} {'Reason'}")
        print(f"  {'-'*80}")
        for row in latest:
            static = CONVERGENCE_WEIGHTS.get(row["module_name"], 0)
            delta = row["weight"] - static
            delta_str = f"{delta:+.3f}" if abs(delta) >= 0.001 else "  ─"
            print(f"  {row['module_name']:<22} {static:>6.3f} {row['weight']:>8.4f} {delta_str:>7} {row['reason'] or ''}")
    else:
        print("\n  No adaptive weights computed yet.")

    # Weight history timeline
    history = query(
        """SELECT date, COUNT(DISTINCT module_name) as modules,
                  SUM(ABS(weight - prior_weight)) as total_delta
           FROM weight_history
           WHERE regime = 'all'
           GROUP BY date
           ORDER BY date DESC
           LIMIT 10"""
    )
    if history:
        print(f"\n  ── WEIGHT HISTORY (last 10 updates) ──")
        print(f"  {'Date':<12} {'Modules':>8} {'Total Delta':>12}")
        for h in history:
            print(f"  {h['date']:<12} {h['modules']:>8} {h['total_delta']:>+11.4f}")

    # Optimizer log
    logs = query(
        "SELECT date, action, details FROM weight_optimizer_log ORDER BY date DESC LIMIT 5"
    )
    if logs:
        print(f"\n  ── RECENT LOG ──")
        for log in logs:
            details = json.loads(log["details"]) if log["details"] else {}
            print(f"  {log['date']} | {log['action']} | {json.dumps(details)[:60]}")

    print("\n" + "=" * 70)


def run():
    """Daily run: check sufficiency, optimize if possible."""
    init_db()

    print("\n" + "=" * 60)
    print("  ADAPTIVE WEIGHT OPTIMIZER")
    print("=" * 60)

    if not WO_ENABLE_ADAPTIVE:
        print("  Adaptive weights DISABLED (WO_ENABLE_ADAPTIVE = False)")
        print("=" * 60)
        return

    changes = optimize_weights()

    if changes is None:
        print("  Keeping static weights (insufficient data)")
    elif not changes:
        print("  No weight changes needed (performance aligned with priors)")
    else:
        total_changes = sum(len(c) for c in changes.values())
        print(f"\n  Weight updates applied across {len(changes)} regime(s):")
        for regime, regime_changes in changes.items():
            print(f"\n    Regime: {regime}")
            for c in sorted(regime_changes, key=lambda x: abs(x["delta"]), reverse=True)[:5]:
                sharpe_str = f"sharpe={c['sharpe']:.3f}" if c["sharpe"] else "no sharpe"
                print(f"      {c['module']:<20} {c['prior']:.3f} → {c['new']:.3f} ({c['delta']:+.3f}) [{sharpe_str}, n={c['n_obs']}]")

    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()

    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print_status()
    else:
        run()
