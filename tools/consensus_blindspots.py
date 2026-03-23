"""Consensus Blindspots — Howard Marks' second-level thinking, quantified.
Five sub-signals weighted into composite cbs_score (0-100)."""
import sys, logging, json
from datetime import date
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import numpy as np
from tools.config import (CBS_SENTIMENT_WEIGHT, CBS_CONSENSUS_GAP_WEIGHT, CBS_POSITIONING_WEIGHT,
    CBS_DIVERGENCE_WEIGHT, CBS_FAT_PITCH_WEIGHT, CBS_SHORT_INTEREST_HIGH, CBS_SHORT_INTEREST_LOW,
    CBS_INST_OWNERSHIP_HIGH, CBS_INST_OWNERSHIP_LOW, CBS_DIVERGENCE_THRESHOLD, CBS_FAT_PITCH_MIN_SIGNALS)
from tools.db import init_db, upsert_many, query
logger = logging.getLogger(__name__)

def _fetch_fred(sid, days=365*5):
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return query("SELECT date, value FROM macro_indicators WHERE indicator_id = ? AND date >= ? ORDER BY date ASC", [sid, cutoff])

def _vix_percentile():
    rows = query("SELECT close FROM price_data WHERE symbol = '^VIX' AND date >= date('now', '-1260 days') ORDER BY date ASC")
    if not rows or len(rows) < 60: return None
    values = [r["close"] for r in rows if r["close"] is not None]
    if not values: return None
    return round(sum(1 for v in values if v <= values[-1]) / len(values) * 100, 1)

def _vix_term_structure():
    vix = query("SELECT close FROM price_data WHERE symbol = '^VIX' ORDER BY date DESC LIMIT 1")
    vix3m = query("SELECT close FROM price_data WHERE symbol = '^VIX3M' ORDER BY date DESC LIMIT 1")
    if not vix or not vix3m: return None
    v, v3 = vix[0]["close"], vix3m[0]["close"]
    return round(v / v3, 3) if v and v3 and v3 != 0 else None

def _aaii_sentiment():
    result = {"bull_bear_ratio": None, "umich_zscore": None}
    umich = _fetch_fred("UMCSENT", days=365 * 10)
    if umich and len(umich) >= 24:
        vals = [r["value"] for r in umich if r["value"] is not None]
        if vals:
            mean, std = float(np.mean(vals)), float(np.std(vals))
            if std > 0: result["umich_zscore"] = round((vals[-1] - mean) / std, 2)
    aaii = query("SELECT value FROM economic_dashboard WHERE indicator_id = 'AAII_BULLISH' ORDER BY date DESC LIMIT 1")
    if aaii and aaii[0]["value"] is not None: result["aaii_bullish"] = aaii[0]["value"]
    return result

def _margin_debt_growth():
    rows = _fetch_fred("BOGZ1FL663067003Q", days=365 * 3)
    if not rows or len(rows) < 4: return None
    vals = [r["value"] for r in rows if r["value"] is not None]
    if len(vals) < 4: return None
    return round((vals[-1] - vals[-4]) / vals[-4] * 100, 1) if vals[-4] and vals[-4] > 0 else None

def _money_market_fund_flows():
    rows = _fetch_fred("WRMFNS", days=365 * 3)
    if not rows or len(rows) < 12: return None
    vals = [r["value"] for r in rows if r["value"] is not None]
    if len(vals) < 12: return None
    ref = vals[-26] if len(vals) >= 26 else vals[0]
    return round((vals[-1] - ref) / ref * 100, 1) if ref and ref > 0 else None

def _put_call_ratio():
    rows = query("SELECT close FROM price_data WHERE symbol IN ('^PCALL', 'PCALL') ORDER BY date DESC LIMIT 1")
    return rows[0]["close"] if rows and rows[0]["close"] is not None else None

def compute_sentiment_cycle():
    result, sc = {}, []
    vp = _vix_percentile(); result["vix_percentile"] = vp
    if vp is not None: sc.append(("vix", 50 - vp, 0.30))
    vt = _vix_term_structure(); result["vix_term_ratio"] = vt
    if vt is not None: sc.append(("vix_term", max(-40, min(40, (1.0 - vt) * 100)), 0.10))
    aaii = _aaii_sentiment(); uz = aaii.get("umich_zscore"); result["umich_zscore"] = uz
    if uz is not None: sc.append(("umich", max(-40, min(40, uz * 20)), 0.20))
    mg = _margin_debt_growth(); result["margin_debt_growth"] = mg
    if mg is not None: sc.append(("margin_debt", max(-40, min(40, mg * 1.5)), 0.15))
    mf = _money_market_fund_flows(); result["mmf_flow"] = mf
    if mf is not None: sc.append(("mmf", max(-30, min(30, -mf * 2)), 0.15))
    pc = _put_call_ratio(); result["put_call"] = pc
    if pc is not None: sc.append(("put_call", max(-40, min(40, (0.8 - pc) * 100)), 0.10))
    if sc:
        tw = sum(w for _, _, w in sc)
        cs = max(-100, min(100, sum(s * w for _, s, w in sc) / tw))
    else:
        rr = query("SELECT total_score FROM macro_scores ORDER BY date DESC LIMIT 1")
        cs = rr[0]["total_score"] if rr else 0
    result["cycle_score"] = round(cs, 1)
    result["cycle_position"] = "extreme_fear" if cs <= -40 else "fear" if cs <= -15 else "neutral" if cs <= 15 else "greed" if cs <= 40 else "extreme_greed"
    return result

def compute_consensus_gap(symbol, our_score, analyst_data):
    result = {"consensus_gap_score": 0, "gap_type": "unknown"}
    cb = analyst_data.get("buy_pct") or analyst_data.get("finnhub_bullish_pct")
    if cb is None: return result
    we_bull, we_bear = our_score >= 20, our_score < 15
    cvb, cb2, cbe = cb >= 85, cb >= 70, cb <= 30
    gs = 0
    if we_bull and cbe: gs, result["gap_type"] = 40, "contrarian_bullish"
    elif we_bull and not cb2: gs, result["gap_type"] = 20, "ahead_of_consensus"
    elif we_bull and cvb: gs, result["gap_type"] = -30, "crowded_agreement"
    elif we_bull and cb2: gs, result["gap_type"] = -15, "consensus_aligned"
    elif we_bear and cvb: gs, result["gap_type"] = 10, "contrarian_bearish_warning"
    elif we_bear and cbe: gs, result["gap_type"] = -10, "consensus_aligned_bearish"
    elif 15 <= our_score < 20: gs, result["gap_type"] = 0, "neutral"
    tu = analyst_data.get("target_upside")
    if tu is not None:
        if tu < 0.03 and we_bull: gs -= 10
        elif tu > 0.30 and we_bull: gs += 5
    result["consensus_gap_score"] = max(-50, min(50, gs))
    return result

def compute_positioning_extremes(symbol, short_data, analyst_data):
    score, flags = 0, []
    si = short_data.get("short_interest_pct")
    if si is not None:
        if si >= CBS_SHORT_INTEREST_HIGH: score += 25; flags.append("heavy_short_interest")
        elif si >= 10: score += 10; flags.append("elevated_short_interest")
        elif si <= CBS_SHORT_INTEREST_LOW: score -= 10; flags.append("minimal_short_interest")
    sr = short_data.get("short_ratio")
    if sr is not None:
        if sr >= 8: score += 15; flags.append("high_days_to_cover")
        elif sr >= 5: score += 5
    ip = short_data.get("institutional_pct")
    if ip is not None:
        if ip >= CBS_INST_OWNERSHIP_HIGH: score -= 15; flags.append("crowded_institutional")
        elif ip <= CBS_INST_OWNERSHIP_LOW: score += 15; flags.append("underfollowed")
    bp, sp, rc = analyst_data.get("buy_pct"), analyst_data.get("sell_pct"), analyst_data.get("rating_count")
    if bp is not None and rc and rc >= 5:
        if bp >= 90: score -= 20; flags.append("analyst_unanimity_buy")
        elif sp is not None and sp >= 60: score += 20; flags.append("analyst_widely_hated")
    return {"positioning_score": max(-50, min(50, score)), "positioning_flags": flags}

def compute_signal_divergence(symbol, module_scores):
    result = {"divergence_score": 0, "divergence_type": "none", "divergence_magnitude": 0}
    fund_mods = ["smartmoney", "worldview", "variant", "research", "estimate_momentum", "ma"]
    mom_mods = ["main_signal", "pattern_options", "pairs", "sector_expert", "news_displacement"]
    fa = [s for m in fund_mods if (s := module_scores.get(m, {}).get(symbol, 0)) > 0]
    ma = [s for m in mom_mods if (s := module_scores.get(m, {}).get(symbol, 0)) > 0]
    if not fa and not ma: return result
    favg, mavg = (float(np.mean(fa)) if fa else 0), (float(np.mean(ma)) if ma else 0)
    div = abs(favg - mavg); result["divergence_magnitude"] = round(div, 1)
    if div < CBS_DIVERGENCE_THRESHOLD: result["divergence_type"] = "aligned"; return result
    if favg > mavg + CBS_DIVERGENCE_THRESHOLD: result["divergence_score"] = min(25, int(div * 0.5)); result["divergence_type"] = "accumulation"
    elif mavg > favg + CBS_DIVERGENCE_THRESHOLD: result["divergence_score"] = -min(20, int(div * 0.4)); result["divergence_type"] = "distribution"
    return result

def compute_fat_pitch(symbol, cycle_score, module_scores, our_convergence, insider_score_override=None):
    conds, anti = [], []
    if cycle_score <= -30: conds.append("extreme_fear")
    elif cycle_score <= -15: conds.append("fear")
    if cycle_score >= 30: anti.append("extreme_greed")
    elif cycle_score >= 15: anti.append("greed")
    v = module_scores.get("variant", {}).get(symbol, 0)
    if v >= 70: conds.append("deep_undervaluation")
    elif v >= 60: conds.append("undervaluation")
    if 0 < v < 30: anti.append("overvaluation")
    sm = module_scores.get("smartmoney", {}).get(symbol, 0)
    if sm >= 65: conds.append("smart_money_buying")
    elif sm >= 55: conds.append("smart_money_interested")
    ins = insider_score_override if insider_score_override is not None else (query("SELECT MAX(insider_score) as score FROM insider_signals WHERE symbol = ? AND date >= date('now', '-30 days')", [symbol])[0]["score"] or 0)
    if ins >= 60: conds.append("insider_buying")
    elif ins >= 40: conds.append("insider_interest")
    if 0 < ins <= 15: anti.append("insider_selling")
    if our_convergence >= 22: conds.append("system_bullish")
    elif our_convergence >= 18: conds.append("system_leaning_bullish")
    cnt, ac = len(conds), len(anti)
    fps = ({3: 40, 4: 70, 5: 90}.get(min(cnt, 5), 90) - ac * 10) if cnt >= CBS_FAT_PITCH_MIN_SIGNALS else cnt * 5
    if ac >= 3: fps = max(0, fps - 30)
    return {"fat_pitch_score": max(0, min(100, fps)), "fat_pitch_conditions": conds, "fat_pitch_count": cnt, "anti_pitch_count": ac, "anti_pitch_conditions": anti}

def compute_cbs_score(sentiment_sub, consensus_gap_sub, positioning_sub, divergence_sub, fat_pitch_sub):
    s = 50.0
    s += max(-15, min(15, -sentiment_sub * CBS_SENTIMENT_WEIGHT * 0.60))
    s += consensus_gap_sub * CBS_CONSENSUS_GAP_WEIGHT * 2.0
    s += positioning_sub * CBS_POSITIONING_WEIGHT * 2.0
    s += divergence_sub * CBS_DIVERGENCE_WEIGHT * 2.0
    s += max(0, (fat_pitch_sub - 20) * CBS_FAT_PITCH_WEIGHT)
    return max(0, min(100, round(s, 1)))

def run(symbols=None):
    init_db()
    print("\n" + "=" * 60 + "\n  CONSENSUS BLINDSPOTS — Second-Level Thinking\n" + "=" * 60)
    print("\n  [1/5] Computing sentiment cycle...")
    cd = compute_sentiment_cycle()
    cs, cp = cd["cycle_score"], cd["cycle_position"]
    print(f"        Cycle: {cs:+.1f} ({cp})")
    if cd["vix_percentile"] is not None: print(f"        VIX pctl: {cd['vix_percentile']:.0f}th")
    print("\n  [2/5] Loading module scores...")
    from tools.convergence_engine import _load_module_scores
    ms = _load_module_scores()
    conv_rows = query("SELECT symbol, convergence_score, module_count, conviction_level FROM convergence_signals WHERE date = (SELECT MAX(date) FROM convergence_signals)")
    cmap = {r["symbol"]: r for r in conv_rows}
    print(f"        {len(cmap)} symbols with convergence scores")
    if symbols is None: symbols = list(cmap.keys())
    print(f"        Analyzing {len(symbols)} symbols")
    _ab, _sb = {}, {}
    for r in query("SELECT symbol, metric, value FROM fundamentals WHERE metric IN ('analyst_buy_pct','analyst_sell_pct','analyst_rating_count','analyst_target_consensus','finnhub_analyst_bullish_pct')"):
        _ab.setdefault(r["symbol"], {})[r["metric"]] = r["value"]
    _pb = {r["symbol"]: r["close"] for r in query("SELECT symbol, close FROM price_data WHERE (symbol, date) IN (SELECT symbol, MAX(date) FROM price_data GROUP BY symbol)") if r["close"]}
    for r in query("SELECT symbol, metric, value FROM fundamentals WHERE metric IN ('short_interest_pct','short_ratio','shares_short','float_shares','institutional_pct')"):
        _sb.setdefault(r["symbol"], {})[r["metric"]] = r["value"]
    _ib = {r["symbol"]: r["score"] for r in query("SELECT symbol, MAX(insider_score) as score FROM insider_signals WHERE date >= date('now', '-30 days') GROUP BY symbol") if r["score"]}
    print("\n  [3/5] Computing per-stock gaps & positioning...")
    today = date.today().isoformat()
    results, fat_pitches, contrarian, crowded, errs = [], [], [], [], 0
    for i, sym in enumerate(symbols):
      try:
        cd2 = cmap.get(sym, {})
        our = cd2.get("convergence_score", 0) if isinstance(cd2, dict) else 0
        ra = _ab.get(sym, {}); price = _pb.get(sym); tgt = ra.get("analyst_target_consensus")
        tu = ((tgt - price) / price) if (price and tgt and price > 0) else None
        ad = {"buy_pct": ra.get("analyst_buy_pct"), "sell_pct": ra.get("analyst_sell_pct"), "rating_count": ra.get("analyst_rating_count"), "target_upside": tu, "finnhub_bullish_pct": ra.get("finnhub_analyst_bullish_pct")}
        gr = compute_consensus_gap(sym, our, ad)
        sd = _sb.get(sym, {})
        pr = compute_positioning_extremes(sym, sd, ad)
        dr = compute_signal_divergence(sym, ms)
        fr = compute_fat_pitch(sym, cs, ms, our, insider_score_override=_ib.get(sym, 0))
        cbs = compute_cbs_score(cs, gr["consensus_gap_score"], pr["positioning_score"], dr["divergence_score"], fr["fat_pitch_score"])
        parts = []
        if gr["gap_type"] not in ("unknown", "neutral"): parts.append(gr["gap_type"])
        if pr["positioning_flags"]: parts.append("|".join(pr["positioning_flags"][:2]))
        if dr["divergence_type"] != "none": parts.append(f"div:{dr['divergence_type']}")
        if fr["fat_pitch_count"] >= CBS_FAT_PITCH_MIN_SIGNALS: parts.append(f"FAT_PITCH({fr['fat_pitch_count']})")
        narr = f"[{cp}] {' | '.join(parts)}" if parts else f"[{cp}] no_signal"
        results.append((sym, today, cbs, cs, cp, gr["consensus_gap_score"], gr["gap_type"], pr["positioning_score"], json.dumps(pr["positioning_flags"]),
            dr["divergence_score"], dr["divergence_type"], dr["divergence_magnitude"], fr["fat_pitch_score"], fr["fat_pitch_count"],
            json.dumps(fr["fat_pitch_conditions"]), fr["anti_pitch_count"], json.dumps(fr.get("anti_pitch_conditions", [])),
            ad.get("buy_pct"), ad.get("sell_pct"), ad.get("target_upside"), sd.get("short_interest_pct"), sd.get("institutional_pct"), our, narr))
        if cbs >= 65: contrarian.append((sym, cbs, gr["gap_type"], fr["fat_pitch_count"]))
        if fr["fat_pitch_count"] >= 3: fat_pitches.append((sym, cbs, fr["fat_pitch_count"], fr["fat_pitch_conditions"]))
        if gr["gap_type"] == "crowded_agreement": crowded.append((sym, our, ad.get("buy_pct")))
      except Exception as e:
        errs += 1
        if errs <= 5: logger.warning(f"CBS error for {sym}: {e}")
      if (i + 1) % 100 == 0: print(f"        Processed {i + 1}/{len(symbols)}...")
    if errs: print(f"        {errs} errors")
    print("\n  [5/6] Storing results...")
    _cols = ["symbol", "date", "cbs_score", "cycle_score", "cycle_position", "consensus_gap_score", "gap_type",
        "positioning_score", "positioning_flags", "divergence_score", "divergence_type", "divergence_magnitude",
        "fat_pitch_score", "fat_pitch_count", "fat_pitch_conditions", "anti_pitch_count", "anti_pitch_conditions",
        "analyst_buy_pct", "analyst_sell_pct", "analyst_target_upside", "short_interest_pct", "institutional_pct", "our_convergence_score", "narrative"]
    if results: upsert_many("consensus_blindspot_signals", _cols, results)
    upsert_many("consensus_blindspot_signals", _cols,
        [("_MARKET", today, 50, cs, cp, 0, "market_wide", 0, "[]", 0, "none", 0, 0, 0, "[]", 0, "[]", None, None, None, None, None, 0, f"Market sentiment: {cp} ({cs:+.1f})")])
    print(f"\n  [6/6] Summary\n  {'='*58}")
    print(f"  Cycle: {cp.upper()} ({cs:+.1f}) | Analyzed: {len(results)} | Contrarian>=65: {sum(1 for r in results if r[2] >= 65)} | Crowded<=35: {sum(1 for r in results if r[2] <= 35)}")
    if fat_pitches:
        fat_pitches.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  FAT PITCHES ({len(fat_pitches)}):")
        for s, c, n, cds in fat_pitches[:10]: print(f"    {s:>8} | {c:5.0f} | {n} | {', '.join(cds[:3])}")
    if contrarian:
        contrarian.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  TOP CONTRARIAN ({len(contrarian)}):")
        for s, c, gt, fp in contrarian[:15]: print(f"    {s:>8} | {c:5.0f} | {gt:>22} | {fp}")
    if crowded:
        print(f"\n  CROWDED ({len(crowded)}):")
        for s, o, b in crowded[:10]: print(f"    {s:>8} | {o:9.0f} | {b:.0f}" if b else f"    {s:>8} | {o:9.0f} | ?")
    print(f"\n  {'='*58}\n" + "=" * 60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("--symbols", type=str)
    args = p.parse_args()
    run(args.symbols.split(",") if args.symbols else None)
