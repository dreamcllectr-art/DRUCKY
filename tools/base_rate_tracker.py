"""Base Rate Tracker — empirical signal outcome measurement."""
import json, logging, math, sys
from datetime import date, datetime
from tools.db import init_db, get_conn, query, upsert_many
from tools.config import DA_WARNING_THRESHOLD

logger = logging.getLogger(__name__)
ALL_MODULES = ["smartmoney", "worldview", "variant", "research", "news_displacement", "foreign_intel",
    "pairs", "main_signal", "alt_data", "sector_expert", "reddit", "ma", "energy_intel",
    "prediction_markets", "pattern_options", "estimate_momentum", "ai_regulatory", "consensus_blindspots"]
RETURN_WINDOWS = [("return_1d","price_1d",1), ("return_5d","price_5d",5), ("return_10d","price_10d",10),
    ("return_20d","price_20d",20), ("return_30d","price_30d",30), ("return_60d","price_60d",60), ("return_90d","price_90d",90)]

def log_signals():
    today = date.today().isoformat()
    signals = query("SELECT symbol, convergence_score, module_count, conviction_level, active_modules, narrative FROM convergence_signals WHERE date = ? AND conviction_level IN ('HIGH', 'NOTABLE')", [today])
    if not signals: print("  No HIGH/NOTABLE signals to log today"); return 0
    regime_rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime = regime_rows[0]["regime"] if regime_rows else "neutral"
    symbols = [s["symbol"] for s in signals]
    ph = ",".join("?" * len(symbols))
    price_map = {r["symbol"]: r["close"] for r in query(f"SELECT p.symbol, p.close FROM price_data p INNER JOIN (SELECT symbol, MAX(date) as mx FROM price_data WHERE symbol IN ({ph}) AND close IS NOT NULL GROUP BY symbol) m ON p.symbol = m.symbol AND p.date = m.mx", symbols)}
    meta_map = {}
    for r in query(f"SELECT su.symbol, su.sector, f.value as marketCap FROM stock_universe su LEFT JOIN fundamentals f ON f.symbol = su.symbol AND f.metric = 'marketCap' WHERE su.symbol IN ({ph})", symbols):
        mcap = r["marketcap"]
        cap_bucket = "mega" if mcap and mcap > 200e9 else "large" if mcap and mcap > 10e9 else "mid" if mcap and mcap > 2e9 else "small" if mcap else None
        meta_map[r["symbol"]] = (r["sector"], cap_bucket)
    da_map = {r["symbol"]: (r["risk_score"], r["warning_flag"]) for r in query(f"SELECT symbol, risk_score, warning_flag FROM devils_advocate WHERE date = ? AND symbol IN ({ph})", [today] + symbols)}
    logged = 0
    with get_conn() as conn:
        for sig in signals:
            symbol = sig["symbol"]
            entry_price = price_map.get(symbol)
            if entry_price is None: continue
            sector, cap_bucket = meta_map.get(symbol, (None, None))
            da_risk, da_warning = da_map.get(symbol, (None, 0))
            conn.execute("INSERT OR IGNORE INTO signal_outcomes (symbol, signal_date, conviction_level, convergence_score, module_count, active_modules, regime_at_signal, sector, market_cap_bucket, entry_price, da_risk_score, da_warning) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, today, sig["conviction_level"], sig["convergence_score"], sig["module_count"], sig["active_modules"], regime, sector, cap_bucket, entry_price, da_risk, da_warning))
            logged += 1
    print(f"  Logged {logged} new signals (entry prices captured)"); return logged

def update_outcomes():
    updated = {}
    for return_col, price_col, days in RETURN_WINDOWS:
        updated[f"{days}d"] = 0
        stale = query(f"SELECT symbol, signal_date, entry_price FROM signal_outcomes WHERE {return_col} IS NULL AND entry_price IS NOT NULL AND signal_date <= date('now', '-{days} days')")
        if not stale: continue
        with get_conn() as conn:
            for row in stale:
                from datetime import timedelta
                target_dt = (datetime.strptime(row["signal_date"], "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
                price_rows = query("SELECT close FROM price_data WHERE symbol = ? AND date >= ? AND close IS NOT NULL ORDER BY date ASC LIMIT 1", [row["symbol"], target_dt])
                if not price_rows or price_rows[0]["close"] is None: continue
                pct_return = round((price_rows[0]["close"] - row["entry_price"]) / row["entry_price"] * 100, 2)
                conn.execute(f"UPDATE signal_outcomes SET {price_col} = ?, {return_col} = ? WHERE symbol = ? AND signal_date = ?", [price_rows[0]["close"], pct_return, row["symbol"], row["signal_date"]])
                updated[f"{days}d"] += 1
    _check_target_stop()
    total = sum(updated.values())
    if total: print(f"  Updated outcomes: {', '.join(f'{k}={v}' for k, v in updated.items() if v > 0)}")
    else: print("  No outcomes to update (signals not yet aged)")
    return updated

def _check_target_stop():
    unchecked = query("SELECT so.symbol, so.signal_date, so.entry_price FROM signal_outcomes so WHERE so.return_90d IS NOT NULL AND so.hit_target IS NULL")
    if not unchecked: return
    with get_conn() as conn:
        for row in unchecked:
            sig_rows = query("SELECT target_price, stop_loss FROM signals WHERE symbol = ? AND date = ?", [row["symbol"], row["signal_date"]])
            if not sig_rows:
                conn.execute("UPDATE signal_outcomes SET hit_target = 0, hit_stop = 0 WHERE symbol = ? AND signal_date = ?", [row["symbol"], row["signal_date"]]); continue
            target, stop = sig_rows[0].get("target_price"), sig_rows[0].get("stop_loss")
            from datetime import timedelta
            end_dt = (datetime.strptime(row["signal_date"], "%Y-%m-%d") + timedelta(days=90)).strftime("%Y-%m-%d")
            extremes = query("SELECT MAX(high) as max_high, MIN(low) as min_low FROM price_data WHERE symbol = ? AND date > ? AND date <= ?", [row["symbol"], row["signal_date"], end_dt])
            hit_target = 1 if extremes and extremes[0]["max_high"] is not None and target and extremes[0]["max_high"] >= target else 0
            hit_stop = 1 if extremes and extremes[0]["min_low"] is not None and stop and extremes[0]["min_low"] <= stop else 0
            conn.execute("UPDATE signal_outcomes SET hit_target = ?, hit_stop = ? WHERE symbol = ? AND signal_date = ?", [hit_target, hit_stop, row["symbol"], row["signal_date"]])

def _compute_sharpe(returns):
    if len(returns) < 5: return None
    avg = sum(returns) / len(returns)
    variance = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance) if variance > 0 else 0
    return round(avg / std, 2) if std else None

def _ci95(returns):
    n = len(returns)
    if n < 5: return None
    avg = sum(returns) / n
    std_err = math.sqrt(sum((r - avg) ** 2 for r in returns) / (n - 1) / n)
    return (round(avg - 1.96 * std_err, 2), round(avg + 1.96 * std_err, 2))

def generate_report():
    today = date.today().isoformat()
    print("\n" + "=" * 70 + "\n  BASE RATE PERFORMANCE REPORT\n" + "=" * 70)
    n_resolved = 0
    for check_col in ["return_5d", "return_10d", "return_20d", "return_30d"]:
        total = query(f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE {check_col} IS NOT NULL")
        n_resolved = total[0]["cnt"] if total else 0
        if n_resolved >= 10: break
    if n_resolved < 10:
        print(f"\n  Insufficient data: only {n_resolved} resolved signals (need 10+)\n" + "=" * 70); return
    for _, _, days in RETURN_WINDOWS:
        cnt = query(f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE return_{days}d IS NOT NULL")
        n = cnt[0]["cnt"] if cnt else 0
        if n > 0: print(f"  Resolved signals ({days}d): {n}")
    print("\n  -- WIN RATE BY CONVICTION LEVEL --")
    header_periods = ["1d", "5d", "10d", "20d", "30d"]
    print(f"  {'Level':<10} {'N':>5} " + " ".join(f"{'Win'+p:>7}" for p in header_periods))
    for level in ["HIGH", "NOTABLE"]:
        base = query("SELECT COUNT(*) as total FROM signal_outcomes WHERE conviction_level = ? AND (return_5d IS NOT NULL OR return_30d IS NOT NULL)", [level])
        total = base[0]["total"] if base else 0
        if total == 0: continue
        win_pcts = []
        for period in header_periods:
            stats = query(f"SELECT COUNT(*) as total, SUM(CASE WHEN return_{period} > 0 THEN 1 ELSE 0 END) as wins FROM signal_outcomes WHERE conviction_level = ? AND return_{period} IS NOT NULL", [level])
            if stats and stats[0]["total"] > 0: win_pcts.append(f"{(stats[0]['wins'] / stats[0]['total']) * 100:>6.1f}%")
            else: win_pcts.append(f"{'--':>7}")
        print(f"  {level:<10} {total:>5} " + " ".join(win_pcts))
    best_return_col = "return_30d"
    for col in ["return_20d", "return_10d", "return_5d"]:
        cnt = query(f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE {col} IS NOT NULL")
        if cnt and cnt[0]["cnt"] >= 10: best_return_col = col; break
    best_period = best_return_col.replace("return_", "")
    print(f"\n  -- MODULE HIT RATES ({best_period}) --")
    print(f"  {'Module':<22} {'N':>6} {'Win%':>6} {'Avg':>7} {'Sharpe':>7}")
    for module in ALL_MODULES:
        stats = query(f"SELECT COUNT(*) as total, SUM(CASE WHEN {best_return_col} > 0 THEN 1 ELSE 0 END) as wins, AVG({best_return_col}) as avg_ret FROM signal_outcomes WHERE active_modules LIKE ? AND {best_return_col} IS NOT NULL", [f'%"{module}"%'])
        if not stats or stats[0]["total"] == 0: continue
        s = stats[0]; win_pct = (s["wins"] / s["total"]) * 100; avg_ret = s["avg_ret"] or 0
        returns = [r["ret"] for r in query(f"SELECT {best_return_col} as ret FROM signal_outcomes WHERE active_modules LIKE ? AND {best_return_col} IS NOT NULL", [f'%"{module}"%']) if r["ret"] is not None]
        sharpe = _compute_sharpe(returns)
        print(f"  {module:<22} {s['total']:>6} {win_pct:>5.1f}% {avg_ret:>+6.1f}% {sharpe if sharpe is not None else '--':>7}")
        period_avgs = {}
        for _, _, days in RETURN_WINDOWS:
            pavg = query(f"SELECT AVG(return_{days}d) as avg FROM signal_outcomes WHERE active_modules LIKE ? AND return_{days}d IS NOT NULL", [f'%"{module}"%'])
            period_avgs[f"avg_return_{days}d"] = round(pavg[0]["avg"], 2) if pavg and pavg[0]["avg"] else None
        ci = _ci95(returns)
        upsert_many("module_performance", ["report_date", "module_name", "regime", "sector", "total_signals", "win_count", "win_rate", "avg_return_1d", "avg_return_5d", "avg_return_10d", "avg_return_20d", "avg_return_30d", "avg_return_60d", "avg_return_90d", "sharpe_ratio", "observation_count", "confidence_interval_low", "confidence_interval_high"],
            [(today, module, "all", "all", s["total"], s["wins"], round(win_pct, 1), period_avgs.get("avg_return_1d"), period_avgs.get("avg_return_5d"), period_avgs.get("avg_return_10d"), period_avgs.get("avg_return_20d"), period_avgs.get("avg_return_30d"), period_avgs.get("avg_return_60d"), period_avgs.get("avg_return_90d"), sharpe, s["total"], ci[0] if ci else None, ci[1] if ci else None)])
    # Co-occurrence
    print("\n  -- MODULE CO-OCCURRENCE --")
    all_active = query(f"SELECT active_modules FROM signal_outcomes WHERE {best_return_col} IS NOT NULL")
    module_counts = {m: 0 for m in ALL_MODULES}; pair_counts = {}
    for row in all_active:
        try: mods = json.loads(row["active_modules"]) if row["active_modules"] else []
        except (json.JSONDecodeError, TypeError): continue
        mod_set = set(mods) & set(ALL_MODULES)
        for m in mod_set: module_counts[m] += 1
        ml = sorted(mod_set)
        for i, ma in enumerate(ml):
            for mb in ml[i+1:]: pair_counts[(ma, mb)] = pair_counts.get((ma, mb), 0) + 1
    high_co = [(a, b, both/min(module_counts.get(a, 1), module_counts.get(b, 1)), both) for (a, b), both in pair_counts.items() if min(module_counts.get(a, 0), module_counts.get(b, 0)) > 0 and both/min(module_counts.get(a, 1), module_counts.get(b, 1)) > 0.80]
    high_co.sort(key=lambda x: x[2], reverse=True)
    if high_co:
        for a, b, rate, count in high_co[:10]: print(f"    {a} + {b}: {rate:.0%} co-occurrence ({count} signals)")
    else: print("    No high co-occurrence pairs detected")
    # DA validation
    da = query(f"SELECT COUNT(*) as total, SUM(CASE WHEN da_warning = 1 THEN 1 ELSE 0 END) as warned, AVG(CASE WHEN da_warning = 1 THEN {best_return_col} END) as warned_avg, AVG(CASE WHEN da_warning = 0 OR da_warning IS NULL THEN {best_return_col} END) as clean_avg FROM signal_outcomes WHERE {best_return_col} IS NOT NULL AND da_risk_score IS NOT NULL")
    if da and da[0]["total"] > 0:
        s = da[0]
        print(f"\n  -- DEVIL'S ADVOCATE VALIDATION --")
        print(f"  Signals: {s['total']}  Warned: {s['warned'] or 0}")
        if s["warned_avg"] is not None and s["clean_avg"] is not None:
            print(f"  Avg {best_period} return (warned): {s['warned_avg']:+.1f}%  (clean): {s['clean_avg']:+.1f}%")
    print("\n" + "=" * 70)

def run():
    init_db()
    print("\n" + "=" * 60 + "\n  BASE RATE TRACKER\n" + "=" * 60)
    log_signals(); update_outcomes()
    print("=" * 60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); init_db()
    if len(sys.argv) > 1 and sys.argv[1] == "report": generate_report()
    else: run()
