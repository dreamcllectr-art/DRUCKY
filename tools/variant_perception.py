"""Variant Perception Engine — find mispricings via implied growth vs base rates."""

import sys, time, argparse
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

_project_root = str(__import__("pathlib").Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import (
    FMP_API_KEY, DISCOUNT_RATE_BULL, DISCOUNT_RATE_BASE, DISCOUNT_RATE_BEAR,
    SCENARIO_WEIGHTS, TERMINAL_GROWTH_CAP,
    CONSENSUS_CROWDING_NARROW_PCT, CONSENSUS_CROWDING_WIDE_PCT,
    CONSENSUS_HERDING_BUY_THRESH, CONSENSUS_HERDING_SELL_THRESH,
    CONSENSUS_SURPRISE_PERSIST_MIN, CONSENSUS_SURPRISE_PERSIST_BIAS,
    CONSENSUS_TARGET_UPSIDE_CROWDED, CONSENSUS_TARGET_UPSIDE_DEEP,
)
from tools.db import init_db, upsert_many, query, query_df
from tools.fetch_fmp_fundamentals import fmp_get


def _safe(val, default=None):
    try: return float(val) if val is not None else default
    except (ValueError, TypeError): return default


def _cagr(start, end, years):
    if not start or not end or start <= 0 or end <= 0 or years <= 0: return None
    return (end / start) ** (1 / years) - 1


def get_current_regime():
    df = query_df("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    return df.iloc[0]["regime"] if not df.empty else "neutral"


def fetch_historical_financials(symbol):
    return (fmp_get(f"/income-statement/{symbol}", {"period": "annual", "limit": 10}),
            fmp_get(f"/key-metrics/{symbol}", {"period": "annual", "limit": 10}),
            fmp_get(f"/enterprise-values/{symbol}", {"period": "annual", "limit": 1}))


def compute_growth_metrics(income):
    if not income or not isinstance(income, list) or len(income) < 3: return {}
    revenues = [_safe(y.get("revenue")) for y in income]
    metrics, n = {}, len(revenues)
    if n >= 5 and revenues[-5] and revenues[0]:
        c = _cagr(revenues[-1], revenues[0], min(n - 1, 5))
        if c is not None: metrics["variant_revenue_cagr_5y"] = round(c, 4)
    if n >= 3 and revenues[-1] and revenues[0]:
        c = _cagr(revenues[-1], revenues[0], n - 1)
        if c is not None: metrics["variant_revenue_cagr_10y"] = round(c, 4)
    yoy = []
    for i in range(len(revenues) - 1):
        curr, prev = revenues[i], revenues[i + 1]
        if curr and prev and prev > 0: yoy.append((curr - prev) / prev)
    if len(yoy) >= 3: metrics["variant_growth_volatility"] = round(float(np.std(yoy)), 4)
    if len(yoy) >= 4:
        metrics["_growth_p75"] = float(np.percentile(yoy, 75))
        metrics["_growth_p50"] = float(np.percentile(yoy, 50))
        metrics["_growth_p25"] = float(np.percentile(yoy, 25))
    if revenues[0]: metrics["_latest_revenue"] = revenues[0]
    earnings = [_safe(y.get("netIncome")) for y in income]
    if earnings[0]: metrics["_latest_earnings"] = earnings[0]
    return metrics


def compute_implied_growth(income, key_metrics, ev_data):
    if not ev_data or not isinstance(ev_data, list) or not ev_data: return {}
    if not key_metrics or not isinstance(key_metrics, list) or not key_metrics: return {}
    current_ev = _safe(ev_data[0].get("enterpriseValue"))
    if not current_ev or current_ev <= 0: return {}
    fcf_yield = _safe(key_metrics[0].get("freeCashFlowYield"))
    market_cap = _safe(key_metrics[0].get("marketCap"))
    if fcf_yield and market_cap and market_cap > 0: total_fcf = fcf_yield * market_cap
    elif income and income[0]: total_fcf = _safe(income[0].get("operatingIncome"))
    else: return {}
    if not total_fcf or total_fcf <= 0: return {}
    if total_fcf / current_ev <= 0: return {}
    implied_growth = DISCOUNT_RATE_BASE - (total_fcf / current_ev)
    implied_growth = max(-0.10, min(implied_growth, TERMINAL_GROWTH_CAP * 3))
    return {"variant_implied_growth": round(implied_growth, 4), "_current_ev": current_ev, "_current_fcf": total_fcf}


def compute_estimate_bias(symbol):
    data = fmp_get(f"/earnings-surprises/{symbol}")
    if not data or not isinstance(data, list): return {}
    biases = []
    for q in data[:8]:
        actual, estimated = _safe(q.get("actualEarningResult")), _safe(q.get("estimatedEarning"))
        if actual is not None and estimated is not None and abs(estimated) > 0.01:
            biases.append((actual - estimated) / abs(estimated))
    return {"variant_estimate_bias": round(float(np.mean(biases)), 4)} if len(biases) >= 4 else {}


def compute_revision_momentum(symbol):
    estimates = fmp_get(f"/analyst-estimates/{symbol}", {"period": "annual", "limit": 3})
    if not estimates or not isinstance(estimates, list) or len(estimates) < 2: return {}
    est_curr, est_next = estimates[0], estimates[1]
    rev_curr = _safe(est_curr.get("estimatedRevenueAvg"))
    rev_next = _safe(est_next.get("estimatedRevenueAvg"))
    eps_curr = _safe(est_curr.get("estimatedEpsAvg"))
    eps_next = _safe(est_next.get("estimatedEpsAvg"))
    momentum = 0
    if rev_curr and rev_next and rev_curr > 0:
        rg = (rev_next - rev_curr) / rev_curr
        momentum += 30 if rg > 0.10 else (15 if rg > 0.05 else (-20 if rg < -0.05 else 0))
    if eps_curr and eps_next and abs(eps_curr) > 0.01:
        eg = (eps_next - eps_curr) / abs(eps_curr)
        momentum += 30 if eg > 0.15 else (15 if eg > 0.05 else (-20 if eg < -0.10 else 0))
    return {"variant_revision_momentum": max(-100, min(100, momentum)), "_fwd_revenue": rev_curr, "_fwd_eps": eps_curr}


def compute_estimate_crowding(symbol):
    estimates = fmp_get(f"/analyst-estimates/{symbol}", {"period": "annual", "limit": 3})
    if not estimates or not isinstance(estimates, list) or not estimates[0]: return {}
    est = estimates[0]
    metrics = {}
    eps_high, eps_low, eps_avg = _safe(est.get("estimatedEpsHigh")), _safe(est.get("estimatedEpsLow")), _safe(est.get("estimatedEpsAvg"))
    rev_high, rev_low, rev_avg = _safe(est.get("estimatedRevenueHigh")), _safe(est.get("estimatedRevenueLow")), _safe(est.get("estimatedRevenueAvg"))
    if eps_high is not None and eps_low is not None and eps_avg and abs(eps_avg) > 0.01:
        metrics["variant_eps_spread"] = round((eps_high - eps_low) / abs(eps_avg), 4)
    if rev_high is not None and rev_low is not None and rev_avg and rev_avg > 0:
        metrics["variant_rev_spread"] = round((rev_high - rev_low) / rev_avg, 4)
    spreads = [v for k, v in metrics.items() if "spread" in k]
    if spreads:
        avg_s = float(np.mean(spreads))
        if avg_s < CONSENSUS_CROWDING_NARROW_PCT: metrics["variant_crowding_score"] = -30
        elif avg_s < 0.15: metrics["variant_crowding_score"] = -10
        elif avg_s > CONSENSUS_CROWDING_WIDE_PCT: metrics["variant_crowding_score"] = 15
        else: metrics["variant_crowding_score"] = 0
    return metrics


def compute_herding_score(symbol):
    rows = query("SELECT metric, value FROM fundamentals WHERE symbol = ? AND metric IN ('analyst_buy_pct', 'analyst_sell_pct', 'analyst_rating_count')", [symbol])
    if not rows: return {}
    data = {r["metric"]: r["value"] for r in rows}
    buy_pct, sell_pct, count = data.get("analyst_buy_pct"), data.get("analyst_sell_pct"), data.get("analyst_rating_count")
    if count is not None and count < 5: return {}
    metrics, herding = {}, 0
    if buy_pct is not None:
        metrics["variant_buy_pct"] = buy_pct
        herding = -25 if buy_pct >= CONSENSUS_HERDING_BUY_THRESH else (-10 if buy_pct >= 70 else herding)
    if sell_pct is not None:
        metrics["variant_sell_pct"] = sell_pct
        herding = 25 if sell_pct >= CONSENSUS_HERDING_SELL_THRESH else (10 if sell_pct >= 50 else herding)
    if herding != 0: metrics["variant_herding_score"] = herding
    return metrics


def compute_surprise_persistence(symbol):
    data = fmp_get(f"/earnings-surprises/{symbol}")
    if not data or not isinstance(data, list): return {}
    beats, misses, surprises = 0, 0, []
    for q in data[:8]:
        actual, estimated = _safe(q.get("actualEarningResult")), _safe(q.get("estimatedEarning"))
        if actual is not None and estimated is not None and abs(estimated) > 0.01:
            sp = (actual - estimated) / abs(estimated)
            surprises.append(sp)
            if sp > 0: beats += 1
            elif sp < 0: misses += 1
    if len(surprises) < 4: return {}
    metrics = {"variant_beat_rate": round(beats / len(surprises), 2), "variant_miss_rate": round(misses / len(surprises), 2)}
    avg_s = float(np.mean(surprises))
    if beats >= CONSENSUS_SURPRISE_PERSIST_MIN and avg_s > CONSENSUS_SURPRISE_PERSIST_BIAS: metrics["variant_surprise_persistence"] = 20
    elif beats >= 4 and avg_s > 0.03: metrics["variant_surprise_persistence"] = 10
    elif misses >= CONSENSUS_SURPRISE_PERSIST_MIN and avg_s < -CONSENSUS_SURPRISE_PERSIST_BIAS: metrics["variant_surprise_persistence"] = -20
    elif misses >= 4 and avg_s < -0.03: metrics["variant_surprise_persistence"] = -10
    else: metrics["variant_surprise_persistence"] = 0
    return metrics


def compute_target_exhaustion(symbol):
    rows = query("SELECT metric, value FROM fundamentals WHERE symbol = ? AND metric IN ('analyst_target_consensus', 'analyst_target_high', 'analyst_target_low')", [symbol])
    if not rows: return {}
    data = {r["metric"]: r["value"] for r in rows}
    target = data.get("analyst_target_consensus")
    if not target or target <= 0: return {}
    price_row = query("SELECT close FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    if not price_row: return {}
    price = price_row[0]["close"]
    if not price or price <= 0: return {}
    upside = (target - price) / price
    metrics = {"variant_target_upside": round(upside, 4)}
    target_high, target_low = data.get("analyst_target_high"), data.get("analyst_target_low")
    if target_high and target_low and target > 0:
        metrics["variant_target_spread"] = round((target_high - target_low) / target, 4)
    if abs(upside) < CONSENSUS_TARGET_UPSIDE_CROWDED: metrics["variant_target_exhaustion"] = -15
    elif upside < -0.15: metrics["variant_target_exhaustion"] = -20
    elif upside > CONSENSUS_TARGET_UPSIDE_DEEP: metrics["variant_target_exhaustion"] = 10
    else: metrics["variant_target_exhaustion"] = 0
    return metrics


def compute_scenario_fair_value(growth_metrics, implied_metrics, regime):
    fcf = implied_metrics.get("_current_fcf")
    if not fcf or fcf <= 0: return {}
    p75, p50, p25 = growth_metrics.get("_growth_p75"), growth_metrics.get("_growth_p50"), growth_metrics.get("_growth_p25")
    if p50 is None: return {}
    if p75 is None: p75 = p50 * 1.5
    if p25 is None: p25 = p50 * 0.5
    tg_bull = min(p75 * 0.4, TERMINAL_GROWTH_CAP)
    tg_base = min(p50 * 0.4, TERMINAL_GROWTH_CAP * 0.75)
    tg_bear = min(max(p25 * 0.3, 0), TERMINAL_GROWTH_CAP * 0.5)

    def scenario_fv(gr, ma, dr, tg):
        f = fcf
        pv = 0
        for yr in range(1, 6):
            f *= (1 + gr) * ma
            pv += f / (1 + dr) ** yr
        term = f * (1 + tg) / (dr - tg) if dr > tg else f * 20
        return max(pv + term / (1 + dr) ** 5, 0)

    fv_bull = scenario_fv(p75, 1.05, DISCOUNT_RATE_BULL, tg_bull)
    fv_base = scenario_fv(p50, 1.00, DISCOUNT_RATE_BASE, tg_base)
    fv_bear = scenario_fv(p25, 0.92, DISCOUNT_RATE_BEAR, tg_bear)
    weights = SCENARIO_WEIGHTS.get(regime, SCENARIO_WEIGHTS["neutral"])
    prob_fv = fv_bull * weights[0] + fv_base * weights[1] + fv_bear * weights[2]
    current_ev = implied_metrics.get("_current_ev", 0)
    upside = ((prob_fv - current_ev) / current_ev * 100) if current_ev > 0 else 0
    return {"variant_fair_value_bull": round(fv_bull, 0), "variant_fair_value_base": round(fv_base, 0),
            "variant_fair_value_bear": round(fv_bear, 0), "variant_prob_weighted_fv": round(prob_fv, 0),
            "variant_upside_pct": round(upside, 2)}


def compute_variant_score(m):
    score = 50
    up = m.get("variant_upside_pct")
    if up is not None:
        if up > 50: score += 25
        elif up > 30: score += 18
        elif up > 15: score += 10
        elif up > 0: score += 3
        elif up < -30: score -= 20
        elif up < -15: score -= 10
        elif up < 0: score -= 3
    gg = m.get("variant_growth_gap")
    if gg is not None:
        if gg < -0.05: score += 12
        elif gg < -0.02: score += 6
        elif gg > 0.10: score -= 10
        elif gg > 0.05: score -= 5
    for key in ["variant_crowding_score", "variant_herding_score", "variant_surprise_persistence", "variant_target_exhaustion"]:
        v = m.get(key)
        if v is not None: score += v
    bias = m.get("variant_estimate_bias")
    if bias is not None:
        if bias > 0.10: score += 6
        elif bias > 0.05: score += 3
        elif bias < -0.10: score -= 6
        elif bias < -0.05: score -= 3
    rev_mom = m.get("variant_revision_momentum")
    herding = m.get("variant_herding_score")
    if rev_mom is not None:
        hd = 0.5 if (herding is not None and abs(herding) >= 20) else 1.0
        rp = 8 if rev_mom > 30 else (3 if rev_mom > 0 else (-8 if rev_mom < -30 else (-3 if rev_mom < 0 else 0)))
        score += int(rp * hd)
    return max(0, min(100, score))


def _process_symbol(symbol, today, regime):
    """Process a single symbol — designed for ThreadPoolExecutor."""
    income, key_metrics, ev_data = fetch_historical_financials(symbol)
    if not income:
        return None
    growth_m = compute_growth_metrics(income)
    implied_m = compute_implied_growth(income, key_metrics, ev_data)
    bias_m = compute_estimate_bias(symbol)
    revision_m = compute_revision_momentum(symbol)
    crowding_m = compute_estimate_crowding(symbol)
    herding_m = compute_herding_score(symbol)
    persistence_m = compute_surprise_persistence(symbol)
    exhaustion_m = compute_target_exhaustion(symbol)
    all_m = {**growth_m, **implied_m, **bias_m, **revision_m, **crowding_m, **herding_m, **persistence_m, **exhaustion_m}
    implied_g = all_m.get("variant_implied_growth")
    base_g = all_m.get("variant_revenue_cagr_5y") or all_m.get("variant_revenue_cagr_10y")
    if implied_g is not None and base_g is not None:
        all_m["variant_growth_gap"] = round(implied_g - base_g, 4)
    all_m.update(compute_scenario_fair_value(growth_m, implied_m, regime))
    vscore = compute_variant_score(all_m)
    all_m["variant_score"] = vscore
    fund_rows = [(symbol, mn, float(val)) for mn, val in all_m.items() if not mn.startswith("_") and val is not None]
    variant_row = (symbol, today, all_m.get("variant_implied_growth"), base_g,
        all_m.get("variant_growth_gap"), all_m.get("variant_estimate_bias"),
        all_m.get("variant_revision_momentum"), all_m.get("variant_fair_value_bull"),
        all_m.get("variant_fair_value_base"), all_m.get("variant_fair_value_bear"),
        all_m.get("variant_prob_weighted_fv"), all_m.get("variant_upside_pct"), vscore,
        all_m.get("variant_crowding_score"), all_m.get("variant_herding_score"),
        all_m.get("variant_surprise_persistence"), all_m.get("variant_target_exhaustion"),
        all_m.get("variant_beat_rate"), all_m.get("variant_target_upside"))
    top = None
    if vscore >= 65:
        top = (symbol, vscore, all_m.get("variant_upside_pct", 0),
               all_m.get("variant_crowding_score"), all_m.get("variant_herding_score"),
               all_m.get("variant_surprise_persistence"), all_m.get("variant_target_exhaustion"))
    return fund_rows, variant_row, top


def run(symbols=None):
    init_db()
    if not FMP_API_KEY:
        print("  ERROR: FMP_API_KEY not set in .env"); return
    if symbols is None:
        # Priority 1: BUY signals from today
        buy_signals = query("SELECT DISTINCT symbol FROM signals WHERE signal IN ('BUY', 'STRONG BUY') AND date = (SELECT MAX(date) FROM signals)")
        if buy_signals:
            symbols = [r["symbol"] for r in buy_signals]
            print(f"Analyzing {len(symbols)} BUY/STRONG BUY signals for variant perception...")
        else:
            # Priority 2: stocks that passed gate 3+ (sector rotation) — not full universe
            gate_pass = query("SELECT symbol FROM gate_results WHERE date = (SELECT MAX(date) FROM gate_results) AND gate_3 = 1")
            if gate_pass:
                symbols = [r["symbol"] for r in gate_pass]
                print(f"Using gate 3+ passing stocks ({len(symbols)} stocks)...")
            else:
                symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
                print(f"No gate data. Analyzing full universe ({len(symbols)} stocks)...")

    # Cache-gate: skip symbols already computed within last 3 days
    cached = {r["symbol"] for r in query(
        "SELECT DISTINCT symbol FROM variant_analysis WHERE date >= (CURRENT_DATE - INTERVAL '3 days')::text"
    )}
    # Always re-run symbols with recent buy signals (they may have moved)
    priority = {r["symbol"] for r in query(
        "SELECT DISTINCT symbol FROM signals WHERE signal IN ('BUY', 'STRONG BUY') AND date = (SELECT MAX(date) FROM signals)"
    )}
    symbols = [s for s in symbols if s not in cached or s in priority]
    print(f"  After cache-gate: {len(symbols)} symbols need fresh analysis (skipped {len(cached) - len(priority & cached)} cached)")

    regime = get_current_regime()
    print(f"  Macro regime: {regime}")
    today = datetime.now().strftime("%Y-%m-%d")
    all_fund_rows, variant_rows, top_variants = [], [], []
    done = 0

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_process_symbol, sym, today, regime): sym for sym in symbols}
        for fut in as_completed(futures):
            result = fut.result()
            done += 1
            if result is None:
                continue
            fund_rows, variant_row, top = result
            all_fund_rows.extend(fund_rows)
            variant_rows.append(variant_row)
            if top:
                top_variants.append(top)
            if done % 50 == 0:
                print(f"  Processed {done}/{len(symbols)} stocks...")

    upsert_many("fundamentals", ["symbol", "metric", "value"], all_fund_rows)
    upsert_many("variant_analysis",
        ["symbol", "date", "implied_growth", "base_rate_growth", "growth_gap",
         "estimate_bias", "revision_momentum", "fair_value_bull", "fair_value_base",
         "fair_value_bear", "prob_weighted_fv", "upside_pct", "variant_score",
         "crowding_score", "herding_score", "surprise_persistence",
         "target_exhaustion", "beat_rate", "target_upside"], variant_rows)
    print(f"\n  Variant perception complete: {len(variant_rows)} stocks analyzed")
    if top_variants:
        top_variants.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  TOP VARIANT OPPORTUNITIES (score >= 65):")
        print(f"    {'Symbol':10s} | {'VScore':>6s} | {'Upside%':>8s} | {'Crowd':>6s} | {'Herd':>5s} | {'Persist':>7s} | {'Target':>6s}")
        for sym, vs, up, crowd, herd, persist, exhaust in top_variants[:25]:
            cs = f"{crowd:+.0f}" if crowd is not None else "-"
            hs = f"{herd:+.0f}" if herd is not None else "-"
            ps = f"{persist:+.0f}" if persist is not None else "-"
            es = f"{exhaust:+.0f}" if exhaust is not None else "-"
            print(f"    {sym:10s} | {vs:6.0f} | {up:+7.1f}% | {cs:>6s} | {hs:>5s} | {ps:>7s} | {es:>6s}")
    else:
        print("\n  No stocks scored >= 65 on variant perception.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Variant Perception Engine")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--all", action="store_true", help="Analyze full universe")
    args = parser.parse_args()
    sym_list = args.symbols.split(",") if args.symbols else None
    run(sym_list)
