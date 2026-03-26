"""Global Energy Markets Scoring — 10 sub-signals -> per-ticker gem_score 0-100."""
import sys, logging
from datetime import date
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from tools.config import ENERGY_INTEL_TICKERS, GEM_SCORE_WEIGHTS, GEM_UTILITY_TICKERS, GEM_CLEAN_ENERGY_TICKERS
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

def _get_physical_signals() -> dict:
    try:
        from tools.energy_physical_flows import get_eu_storage_signal, get_norway_flow_signal, get_cot_signal, get_storage_surprise_signal
        eu, no, cot, sup = get_eu_storage_signal(), get_norway_flow_signal(), get_cot_signal("NAT_GAS_HH"), get_storage_surprise_signal()
        return {"eu_storage": eu.get("score", 50.0), "norway_flow": no.get("score", 50.0),
                "cot_hh": cot.get("score", 50.0), "storage_surprise": sup.get("score", 50.0),
                "eu_fill_pct": eu.get("fill_pct"), "eu_status": eu.get("status", "normal")}
    except Exception as e:
        logger.warning(f"Physical flow signals unavailable: {e}")
        return {"eu_storage": 50.0, "norway_flow": 50.0, "cot_hh": 50.0, "storage_surprise": 50.0, "eu_fill_pct": None, "eu_status": "normal"}

def _clamp(val, lo=0.0, hi=100.0):
    return max(lo, min(hi, val))

def _compute_term_structure_signal() -> dict[str, float]:
    rows = query("SELECT curve_id, months_out, price FROM global_energy_curves WHERE date = (SELECT MAX(date) FROM global_energy_curves) ORDER BY curve_id, months_out")
    if not rows:
        return {"crude": 50.0, "natgas": 50.0}
    curves = {}
    for r in rows:
        curves.setdefault(r["curve_id"], []).append((r["months_out"], r["price"]))
    signals = {}
    for cid, pts in curves.items():
        if len(pts) < 2:
            signals[cid] = 50.0; continue
        spread_pct = (pts[-1][1] - pts[0][1]) / pts[0][1] * 100 if pts[0][1] else 0
        signals[cid] = _clamp(50 - spread_pct * 6)
    return {"crude": (signals.get("WTI", 50) + signals.get("BRENT", 50)) / 2, "natgas": signals.get("HH", 50), "ttf": signals.get("TTF", 50)}

def _compute_basis_signal() -> dict[str, float]:
    rows = query("SELECT spread_id, value, assessment FROM global_energy_spreads WHERE date = (SELECT MAX(date) FROM global_energy_spreads)")
    signals = {}
    for r in rows:
        sid, val = r["spread_id"], r["value"] or 0
        if sid == "brent_wti": signals["brent_wti"] = _clamp(30 + val * 5)
        elif sid == "ttf_hh": signals["ttf_hh"] = _clamp(20 + val * 4)
        elif sid == "crack_321": signals["crack_321"] = _clamp(val * 2.5)
        elif sid == "gasoline_crack": signals["gasoline_crack"] = _clamp(val * 3)
        elif sid == "diesel_crack": signals["diesel_crack"] = _clamp(val * 2.5)
    return signals

def _compute_crack_signal() -> dict[str, float]:
    rows = query("SELECT date, value FROM global_energy_spreads WHERE spread_id = 'crack_321' ORDER BY date DESC LIMIT 90")
    if len(rows) < 5:
        return {"level": 50.0, "momentum": 50.0}
    values = [r["value"] for r in rows if r["value"] is not None]
    if not values:
        return {"level": 50.0, "momentum": 50.0}
    avg = sum(values) / len(values)
    std = (sum((v - avg) ** 2 for v in values) / len(values)) ** 0.5
    level = _clamp(values[0] * 2.5)
    momentum = 50.0
    if len(values) >= 5:
        zscore = (sum(values[:5]) / 5 - avg) / std if std > 0 else 0
        momentum = _clamp(50 + zscore * 20)
    return {"level": level, "momentum": momentum}

def _compute_carbon_signal() -> float:
    rows = query("SELECT date, price FROM global_energy_carbon WHERE market_id = 'EU_ETS' ORDER BY date DESC LIMIT 90")
    if len(rows) < 10:
        return 50.0
    prices = [r["price"] for r in rows if r["price"] is not None]
    if len(prices) < 10:
        return 50.0
    avg = sum(prices) / len(prices)
    std = (sum((p - avg) ** 2 for p in prices) / len(prices)) ** 0.5
    return _clamp(50 - ((prices[0] - avg) / std if std > 0 else 0) * 15)

def _compute_momentum_signal() -> dict[str, float]:
    signals = {}
    for bm_id in ["BRENT", "WTI", "HH", "TTF"]:
        rows = query("SELECT date, close FROM global_energy_benchmarks WHERE benchmark_id = ? AND close IS NOT NULL ORDER BY date DESC LIMIT 22", [bm_id])
        if len(rows) < 5:
            signals[bm_id] = 50.0; continue
        cur, wk, mo = rows[0]["close"], rows[4]["close"] if len(rows) > 4 else rows[0]["close"], rows[-1]["close"]
        ret_1w = (cur - wk) / wk * 100 if wk else 0
        ret_1m = (cur - mo) / mo * 100 if mo else 0
        signals[bm_id] = _clamp(50 + ret_1w * 6) * 0.6 + _clamp(50 + ret_1m * 3) * 0.4
    return signals

def _compute_cross_market_signal() -> float:
    rets = {}
    for bm_id in ["WTI", "COPPER"]:
        rows = query("SELECT close FROM global_energy_benchmarks WHERE benchmark_id = ? AND close IS NOT NULL ORDER BY date DESC LIMIT 22", [bm_id])
        if len(rows) < 10:
            return 50.0
        rets[bm_id] = (rows[0]["close"] - rows[-1]["close"]) / rows[-1]["close"] * 100 if rows[-1]["close"] else 0
    cr, cu = rets.get("WTI", 0), rets.get("COPPER", 0)
    if cr > 0 and cu > 0: return _clamp(60 + min(cr, cu) * 3)
    elif cr < 0 and cu < 0: return _clamp(40 + max(cr, cu) * 3)
    elif cr > 0: return _clamp(45 + cr)
    else: return _clamp(50 + cu * 2)

def _score_ticker(symbol, category, ts, basis, crack, carbon, momentum, xm, phys) -> tuple[float, str]:
    w = GEM_SCORE_WEIGHTS
    eu, no, cot, surp = phys.get("eu_storage", 50.0), phys.get("norway_flow", 50.0), phys.get("cot_hh", 50.0), phys.get("storage_surprise", 50.0)
    if category == "upstream":
        t, bwt = ts.get("crude", 50), basis.get("brent_wti", 50)
        mom = (momentum.get("BRENT", 50) + momentum.get("WTI", 50)) / 2
        score = t*w["term_structure"] + bwt*w["basis_spread"] + 50*w["crack_spread"] + carbon*w["carbon"] + mom*w["momentum"] + xm*w["cross_market"] + eu*w["eu_storage"] + cot*w["cot_positioning"] + no*w["norway_flow"] + surp*w["storage_surprise"]
        narr = f"Upstream: ts={t:.0f} basis={bwt:.0f} mom={mom:.0f} EU_stor={eu:.0f} CoT={cot:.0f}"
    elif category == "downstream":
        cl, cm = crack.get("level", 50), crack.get("momentum", 50)
        gc, dc = basis.get("gasoline_crack", 50), basis.get("diesel_crack", 50)
        cc = cl*0.5 + cm*0.2 + gc*0.15 + dc*0.15
        score = 50*w["term_structure"]*0.5 + 50*w["basis_spread"]*0.5 + cc*(w["crack_spread"]+w["term_structure"]*0.5+w["basis_spread"]*0.5) + carbon*w["carbon"] + momentum.get("WTI",50)*w["momentum"]*0.3 + xm*w["cross_market"] + eu*w["eu_storage"]*0.5 + cot*w["cot_positioning"] + 50*w["norway_flow"] + surp*w["storage_surprise"]
        if momentum.get("WTI", 50) > 60:
            score -= (momentum["WTI"] - 60) * 0.3
        score = _clamp(score)
        narr = f"Refiner: crack={cl:.0f} crack_mom={cm:.0f} EU_stor={eu:.0f}"
    elif category == "midstream":
        t, bwt, mom = ts.get("crude", 50), basis.get("brent_wti", 50), momentum.get("WTI", 50)
        score = t*w["term_structure"]*0.5 + bwt*(w["basis_spread"]+w["term_structure"]*0.5) + 50*w["crack_spread"] + carbon*w["carbon"] + mom*w["momentum"] + xm*w["cross_market"] + eu*w["eu_storage"]*0.7 + cot*w["cot_positioning"] + no*(w["norway_flow"]+w["storage_surprise"]*0.5) + surp*w["storage_surprise"]*0.5
        narr = f"Midstream: basis={bwt:.0f} mom={mom:.0f} Norway={no:.0f}"
    elif category == "ofs":
        t = ts.get("crude", 50)
        mom = (momentum.get("BRENT", 50) + momentum.get("WTI", 50)) / 2
        score = t*(w["term_structure"]+w["basis_spread"]) + 50*w["crack_spread"] + carbon*w["carbon"] + mom*(w["momentum"]+w["cross_market"]) + eu*w["eu_storage"]*0.6 + cot*w["cot_positioning"] + 50*w["norway_flow"] + surp*w["storage_surprise"]*0.8
        narr = f"OFS: ts={t:.0f} mom={mom:.0f} EU_stor={eu:.0f}"
    elif category == "lng":
        ttf_hh, ttf_ts = basis.get("ttf_hh", 50), ts.get("ttf", 50)
        ttf_mom, hh_mom = momentum.get("TTF", 50), momentum.get("HH", 50)
        lng_eu, lng_no = 100 - eu, 100 - no
        score = ttf_ts*w["term_structure"] + ttf_hh*(w["basis_spread"]+w["crack_spread"]) + carbon*w["carbon"] + (ttf_mom*0.5+hh_mom*0.5)*w["momentum"] + xm*w["cross_market"] + lng_eu*w["eu_storage"] + cot*w["cot_positioning"] + lng_no*w["norway_flow"] + surp*w["storage_surprise"]
        narr = f"LNG: ttf_hh={ttf_hh:.0f} EU_stor(inv)={lng_eu:.0f} Norway(inv)={lng_no:.0f}"
    elif category == "utility":
        gas_cost = (momentum.get("HH", 50) + momentum.get("TTF", 50)) / 2
        gs, cs = 100 - gas_cost, carbon
        score = 50*w["term_structure"] + 50*w["basis_spread"] + 50*w["crack_spread"] + cs*(w["carbon"]+w["basis_spread"]) + gs*(w["momentum"]+w["term_structure"]) + xm*w["cross_market"] + eu*w["eu_storage"] + cot*w["cot_positioning"] + no*w["norway_flow"] + surp*w["storage_surprise"]
        narr = f"Utility: gas={gs:.0f} carbon={cs:.0f} EU_stor={eu:.0f}"
    elif category == "clean_energy":
        ct, hh_mom = 100 - carbon, momentum.get("HH", 50)
        eu_clean = 100 - eu
        score = 50*w["term_structure"] + 50*w["basis_spread"] + 50*w["crack_spread"] + ct*(w["carbon"]+w["crack_spread"]+w["basis_spread"]) + hh_mom*(w["momentum"]+w["term_structure"]) + xm*w["cross_market"] + eu_clean*w["eu_storage"] + cot*w["cot_positioning"] + 50*w["norway_flow"] + surp*w["storage_surprise"]*0.5
        narr = f"Clean: carbon_tw={ct:.0f} gas_sup={hh_mom:.0f} EU_tight={eu_clean:.0f}"
    else:
        score, narr = 50.0, "No category match"
    return _clamp(score), narr

def compute_gem_adjustments() -> dict[str, float]:
    rows = query("SELECT symbol, MAX(gem_score) as gem_score FROM global_energy_signals WHERE date >= date('now', '-7 days') GROUP BY symbol")
    return {r["symbol"]: r["gem_score"] for r in rows if r["gem_score"]}

def run():
    init_db()
    print("\n  === GLOBAL ENERGY MARKETS SCORING (10 sub-signals) ===")
    ts = _compute_term_structure_signal()
    basis = _compute_basis_signal()
    crack = _compute_crack_signal()
    carbon = _compute_carbon_signal()
    mom = _compute_momentum_signal()
    xm = _compute_cross_market_signal()
    phys = _get_physical_signals()
    print(f"  Original 6: ts_crude={ts.get('crude',50):.1f} ts_ttf={ts.get('ttf',50):.1f} basis_bwt={basis.get('brent_wti',50):.1f} ttf_hh={basis.get('ttf_hh',50):.1f} crack={crack.get('level',50):.1f} carbon={carbon:.1f} xm={xm:.1f}")
    print(f"  Physical 4: EU_stor={phys['eu_storage']:.1f} Norway={phys['norway_flow']:.1f} CoT={phys['cot_hh']:.1f} Surprise={phys['storage_surprise']:.1f}")
    today_str, results = date.today().isoformat(), []
    for category, tickers in ENERGY_INTEL_TICKERS.items():
        for symbol in tickers:
            score, narr = _score_ticker(symbol, category, ts, basis, crack, carbon, mom, xm, phys)
            results.append((symbol, today_str, score, category, ts.get("crude", 50), basis.get("brent_wti", 50), crack.get("level", 50), carbon, narr))
    for symbol in GEM_UTILITY_TICKERS:
        score, narr = _score_ticker(symbol, "utility", ts, basis, crack, carbon, mom, xm, phys)
        results.append((symbol, today_str, score, "utility", ts.get("natgas", 50), basis.get("ttf_hh", 50), 50.0, carbon, narr))
    for symbol in GEM_CLEAN_ENERGY_TICKERS:
        score, narr = _score_ticker(symbol, "clean_energy", ts, basis, crack, carbon, mom, xm, phys)
        results.append((symbol, today_str, score, "clean_energy", 50.0, 50.0, 50.0, carbon, narr))
    if results:
        upsert_many("global_energy_signals", ["symbol", "date", "gem_score", "category", "term_structure_signal", "basis_signal", "crack_signal", "carbon_signal", "narrative"], results)
    scores = [r[2] for r in results]
    if scores:
        avg, above = sum(scores)/len(scores), sum(1 for s in scores if s >= 50)
        print(f"\n  Results: {len(results)} tickers | avg={avg:.1f} | bullish={above} | bearish={len(scores)-above}")
        by_cat: dict = {}
        for r in results:
            by_cat.setdefault(r[3], []).append(r)
        for cat in sorted(by_cat):
            top = sorted(by_cat[cat], key=lambda r: r[2], reverse=True)[:3]
            print(f"\n  {cat.upper()}:")
            for r in top:
                print(f"    {r[0]:6s}: {r[2]:5.1f} — {r[8]}")
    print("  === GLOBAL ENERGY SCORING COMPLETE ===\n")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
