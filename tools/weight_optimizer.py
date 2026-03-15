"""Adaptive Weight Optimizer — the data moat flywheel.
Reads empirical module performance from base_rate_tracker outcomes,
computes Bayesian-updated weights, and writes them to weight_history."""
import json, logging, math
from datetime import date, datetime
from tools.db import init_db, get_conn, query, upsert_many
from tools.config import (CONVERGENCE_WEIGHTS, REGIME_CONVERGENCE_WEIGHTS, WO_MIN_WEIGHT,
    WO_MAX_WEIGHT, WO_MIN_OBSERVATIONS, WO_MAX_DELTA_PER_CYCLE, WO_LEARNING_RATE,
    WO_MIN_TOTAL_SIGNALS, WO_MIN_DAYS_RUNNING, WO_ENABLE_ADAPTIVE, WO_HOLDOUT_MODULES)
logger = logging.getLogger(__name__)

def _check_data_sufficiency() -> dict:
    total = query("SELECT COUNT(*) as cnt FROM signal_outcomes WHERE return_5d IS NOT NULL OR return_10d IS NOT NULL OR return_20d IS NOT NULL OR return_30d IS NOT NULL")
    total_resolved = total[0]["cnt"] if total else 0
    first = query("SELECT MIN(signal_date) as first_date FROM signal_outcomes")
    days_running = (date.today() - datetime.strptime(first[0]["first_date"], "%Y-%m-%d").date()).days if first and first[0]["first_date"] else 0
    modules_ok = 0
    for module in CONVERGENCE_WEIGHTS:
        if module in WO_HOLDOUT_MODULES: continue
        cnt = query("SELECT COUNT(*) as cnt FROM signal_outcomes WHERE active_modules LIKE ? AND return_5d IS NOT NULL", [f'%"{module}"%'])
        if cnt and cnt[0]["cnt"] >= WO_MIN_OBSERVATIONS: modules_ok += 1
    result = {"total_resolved": total_resolved, "days_running": days_running, "modules_with_data": modules_ok, "sufficient": True, "reason": None}
    if total_resolved < WO_MIN_TOTAL_SIGNALS:
        result.update(sufficient=False, reason=f"Need {WO_MIN_TOTAL_SIGNALS} resolved signals, have {total_resolved}")
    elif days_running < WO_MIN_DAYS_RUNNING:
        result.update(sufficient=False, reason=f"Need {WO_MIN_DAYS_RUNNING} days of data, have {days_running}")
    elif modules_ok < 5:
        result.update(sufficient=False, reason=f"Need 5+ modules with {WO_MIN_OBSERVATIONS}+ observations, have {modules_ok}")
    return result

def _get_module_performance(regime: str = "all") -> dict[str, dict]:
    best_col = "return_30d"
    for col in ["return_20d", "return_10d", "return_5d"]:
        cnt = query(f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE {col} IS NOT NULL")
        if cnt and cnt[0]["cnt"] >= 20: best_col = col; break
    results = {}
    for module in CONVERGENCE_WEIGHTS:
        if module in WO_HOLDOUT_MODULES: continue
        regime_filter, params = "", [f'%"{module}"%']
        if regime != "all": regime_filter = "AND regime_at_signal = ?"; params.append(regime)
        stats = query(f"SELECT COUNT(*) as total, SUM(CASE WHEN {best_col} > 0 THEN 1 ELSE 0 END) as wins, AVG({best_col}) as avg_ret FROM signal_outcomes WHERE active_modules LIKE ? AND {best_col} IS NOT NULL {regime_filter}", params)
        if not stats or stats[0]["total"] < 5: continue
        s = stats[0]
        win_rate = (s["wins"] / s["total"]) * 100 if s["total"] else 0
        ret_rows = query(f"SELECT {best_col} as ret FROM signal_outcomes WHERE active_modules LIKE ? AND {best_col} IS NOT NULL {regime_filter}", params)
        returns = [r["ret"] for r in ret_rows if r["ret"] is not None]
        sharpe = None
        if len(returns) >= 5:
            avg = sum(returns) / len(returns)
            var = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
            std = math.sqrt(var) if var > 0 else 0
            if std > 0: sharpe = avg / std
        results[module] = {"win_rate": win_rate, "avg_return": s["avg_ret"] or 0, "sharpe": sharpe, "n_observations": s["total"]}
    return results

def _compute_optimal_weights(prior_weights, performance, regime):
    alpha = WO_LEARNING_RATE
    sharpes = {m: p["sharpe"] for m, p in performance.items() if p["sharpe"] is not None and p["n_observations"] >= WO_MIN_OBSERVATIONS}
    if len(sharpes) < 5: return prior_weights
    sv = sorted(sharpes.values())
    mid = len(sv) // 2
    median_sharpe = sv[mid] if len(sv) % 2 else (sv[mid - 1] + sv[mid]) / 2
    new_weights = {}
    for module, prior in prior_weights.items():
        if module in WO_HOLDOUT_MODULES: new_weights[module] = prior; continue
        posterior = prior * (1 + alpha * (sharpes[module] - median_sharpe)) if module in sharpes else prior
        posterior = max(WO_MIN_WEIGHT, min(WO_MAX_WEIGHT, posterior))
        delta = posterior - prior
        if abs(delta) > WO_MAX_DELTA_PER_CYCLE:
            posterior = prior + (WO_MAX_DELTA_PER_CYCLE if delta > 0 else -WO_MAX_DELTA_PER_CYCLE)
        new_weights[module] = posterior
    total = sum(new_weights.values())
    if total > 0: new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}
    return new_weights

def _get_prior_weights(regime):
    rows = query("SELECT module_name, weight FROM weight_history WHERE regime = ? AND date = (SELECT MAX(date) FROM weight_history WHERE regime = ?)", [regime, regime])
    if rows and len(rows) >= 10: return {r["module_name"]: r["weight"] for r in rows}
    return REGIME_CONVERGENCE_WEIGHTS.get(regime, dict(CONVERGENCE_WEIGHTS))

def optimize_weights():
    today = date.today().isoformat()
    sufficiency = _check_data_sufficiency()
    if not sufficiency["sufficient"]:
        print(f"  Data insufficient: {sufficiency['reason']}")
        print(f"    Resolved: {sufficiency['total_resolved']} | Days: {sufficiency['days_running']} | Modules w/{WO_MIN_OBSERVATIONS}+ obs: {sufficiency['modules_with_data']}")
        upsert_many("weight_optimizer_log", ["date", "action", "details"], [(today, "skip_insufficient_data", json.dumps(sufficiency))])
        return None
    regimes = list(REGIME_CONVERGENCE_WEIGHTS.keys()) + ["all"]
    all_changes = {}
    for regime in regimes:
        performance = _get_module_performance(regime)
        if len(performance) < 5: continue
        prior = dict(CONVERGENCE_WEIGHTS) if regime == "all" else _get_prior_weights(regime)
        optimal = _compute_optimal_weights(prior, performance, regime)
        changes = [{"module": m, "prior": prior.get(m, 0), "new": optimal[m], "delta": optimal[m] - prior.get(m, 0),
            "sharpe": performance.get(m, {}).get("sharpe"), "n_obs": performance.get(m, {}).get("n_observations", 0)}
            for m in optimal if abs(optimal[m] - prior.get(m, 0)) >= 0.001]
        rows = []
        for module, weight in optimal.items():
            prior_w = prior.get(module, 0)
            delta = weight - prior_w
            parts = []
            perf = performance.get(module, {})
            if perf.get("sharpe") is not None: parts.append(f"sharpe={perf['sharpe']:.3f}")
            if perf.get("n_observations"): parts.append(f"n={perf['n_observations']}")
            if abs(delta) >= 0.001: parts.append(f"delta={delta:+.4f}")
            rows.append((today, regime, module, round(weight, 4), round(prior_w, 4), ", ".join(parts) or "no change"))
        if rows: upsert_many("weight_history", ["date", "regime", "module_name", "weight", "prior_weight", "reason"], rows)
        if changes: all_changes[regime] = changes
    upsert_many("weight_optimizer_log", ["date", "action", "details"],
        [(today, "optimize_complete", json.dumps({"regimes_optimized": len(all_changes), "total_changes": sum(len(c) for c in all_changes.values()), "sufficiency": sufficiency}))])
    return all_changes

def print_status():
    print("\n" + "=" * 70 + "\n  ADAPTIVE WEIGHT OPTIMIZER — STATUS\n" + "=" * 70)
    s = _check_data_sufficiency()
    print(f"\n  Data Sufficiency: {'YES' if s['sufficient'] else 'NO'}")
    print(f"    Resolved: {s['total_resolved']} (need {WO_MIN_TOTAL_SIGNALS}) | Days: {s['days_running']} (need {WO_MIN_DAYS_RUNNING}) | Modules w/{WO_MIN_OBSERVATIONS}+ obs: {s['modules_with_data']}")
    if not s["sufficient"]: print(f"    Reason: {s['reason']}")
    latest = query("SELECT module_name, weight, prior_weight, reason FROM weight_history WHERE regime = 'all' AND date = (SELECT MAX(date) FROM weight_history WHERE regime = 'all') ORDER BY weight DESC")
    if latest:
        print(f"\n  {'Module':<22} {'Static':>7} {'Adaptive':>9} {'Delta':>7} Reason\n  {'-'*80}")
        for r in latest:
            static = CONVERGENCE_WEIGHTS.get(r["module_name"], 0)
            d = r["weight"] - static
            print(f"  {r['module_name']:<22} {static:>6.3f} {r['weight']:>8.4f} {f'{d:+.3f}' if abs(d) >= 0.001 else '  -':>7} {r['reason'] or ''}")
    else: print("\n  No adaptive weights computed yet.")
    history = query("SELECT date, COUNT(DISTINCT module_name) as modules, SUM(ABS(weight - prior_weight)) as total_delta FROM weight_history WHERE regime = 'all' GROUP BY date ORDER BY date DESC LIMIT 10")
    if history:
        print(f"\n  {'Date':<12} {'Modules':>8} {'Total Delta':>12}")
        for h in history: print(f"  {h['date']:<12} {h['modules']:>8} {h['total_delta']:>+11.4f}")
    logs = query("SELECT date, action, details FROM weight_optimizer_log ORDER BY date DESC LIMIT 5")
    if logs:
        print(f"\n  RECENT LOG:")
        for log in logs: print(f"  {log['date']} | {log['action']} | {json.dumps(json.loads(log['details']) if log['details'] else {})[:60]}")
    print("\n" + "=" * 70)

def run():
    init_db()
    print("\n" + "=" * 60 + "\n  ADAPTIVE WEIGHT OPTIMIZER\n" + "=" * 60)
    if not WO_ENABLE_ADAPTIVE: print("  Adaptive weights DISABLED\n" + "=" * 60); return
    changes = optimize_weights()
    if changes is None: print("  Keeping static weights (insufficient data)")
    elif not changes: print("  No weight changes needed")
    else:
        print(f"\n  Weight updates across {len(changes)} regime(s):")
        for regime, rc in changes.items():
            print(f"\n    Regime: {regime}")
            for c in sorted(rc, key=lambda x: abs(x["delta"]), reverse=True)[:5]:
                sh = f"sharpe={c['sharpe']:.3f}" if c["sharpe"] else "no sharpe"
                print(f"      {c['module']:<20} {c['prior']:.3f} -> {c['new']:.3f} ({c['delta']:+.3f}) [{sh}, n={c['n_obs']}]")
    print("=" * 60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); init_db()
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status": print_status()
    else: run()
