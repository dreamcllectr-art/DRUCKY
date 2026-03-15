"""Energy Intelligence Scoring — supply-demand signals for energy tickers.
Computes energy_intel_score (0-100) per ticker. Sub-signals: inventory (30%),
production (20%), demand (20%), trade flows (15%), global balance (15%)."""
import sys, logging
from datetime import date, datetime
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
from tools.config import (ENERGY_SCORE_WEIGHTS, ENERGY_CUSHING_PREMIUM, ENERGY_INTEL_TICKERS,
    ENERGY_JODI_MAX_LAG_DAYS, ENERGY_JODI_BLEND_WEIGHT, GEM_BLEND_WEIGHT)
from tools.db import init_db, get_conn, query

logger = logging.getLogger(__name__)

def _clamp(val, lo=0.0, hi=100.0): return max(lo, min(hi, val))

def _seasonal_zscore(series_id, table, id_col):
    rows = query(f"SELECT value FROM {table} WHERE {id_col}=? ORDER BY date DESC LIMIT 1", [series_id])
    if not rows: return None
    norms = query("SELECT avg_value,std_value FROM energy_seasonal_norms WHERE series_id=? AND week_of_year=?",
                  [series_id, date.today().isocalendar()[1]])
    if not norms or not norms[0]["std_value"]: return None
    return (rows[0]["value"] - norms[0]["avg_value"]) / norms[0]["std_value"]

def _compute_inventory_signal():
    series = [("PET.WCESTUS1.W","macro_indicators","indicator_id",1.0),
              ("PET.WGTSTUS1.W","macro_indicators","indicator_id",0.6),
              ("PET.WDISTUS1.W","macro_indicators","indicator_id",0.5),
              ("PET.WCESTP21.W","energy_eia_enhanced","series_id",ENERGY_CUSHING_PREMIUM)]
    signals, weights = [], []
    for sid, tbl, col, w in series:
        z = _seasonal_zscore(sid, tbl, col)
        if z is not None:
            signals.append(_clamp(50 - z * 16.67)); weights.append(w)
    if not signals: return 50.0
    return sum(s*w for s,w in zip(signals, weights)) / sum(weights)

def _compute_production_signal():
    rows = query("SELECT value FROM macro_indicators WHERE indicator_id='PET.WCRFPUS2.W' ORDER BY date DESC LIMIT 13")
    if len(rows) < 5: return 50.0
    cur, w4, w12 = rows[0]["value"], rows[4]["value"] if len(rows)>4 else rows[0]["value"], rows[12]["value"] if len(rows)>12 else rows[0]["value"]
    short = ((cur-w4)/w4*100) if w4 else 0
    long = ((cur-w12)/w12*100) if w12 else 0
    return _clamp(50-short*25)*0.6 + _clamp(50-long*12.5)*0.4

def _compute_demand_signal():
    wk = date.today().isocalendar()[1]; signals = []
    z = _seasonal_zscore("PET.WPULEUS3.W", "macro_indicators", "indicator_id")
    if z is not None: signals.append(_clamp(50 + z * 16.67))
    for sid in ["PET.WRPUPUS2.W","PET.WGFUPUS2.W","PET.WDIUPUS2.W"]:
        z = _seasonal_zscore(sid, "energy_eia_enhanced", "series_id")
        if z is not None: signals.append(_clamp(50 + z * 16.67))
    return sum(signals)/len(signals) if signals else 50.0

def _compute_trade_flow_signal():
    signals = []
    for sid, direction, mult in [("PET.WCRRIUS2.W",-1,15),("PET.MCREXUS2.W",1,15)]:
        rows = query(f"SELECT value FROM macro_indicators WHERE indicator_id=? ORDER BY date DESC LIMIT 5", [sid])
        if rows and len(rows) >= 2:
            chg = (rows[0]["value"]-rows[1]["value"])/rows[1]["value"]*100 if rows[1]["value"] else 0
            signals.append(_clamp(50 + direction*chg*mult))
    anomalies = query("""SELECT zscore FROM energy_supply_anomalies
        WHERE anomaly_type IN ('inventory_deficit','inventory_surplus') AND date>=date('now','-7 days')
        AND series_id LIKE 'PET.WCESTP%' AND status='active'""")
    for a in anomalies: signals.append(_clamp(50 - (a["zscore"] or 0)*12))
    z = _seasonal_zscore("PET.WCSDSUS2.W", "energy_eia_enhanced", "series_id")
    if z is not None: signals.append(_clamp(50 - z * 16.67))
    return sum(signals)/len(signals) if signals else 50.0

def _compute_global_balance():
    jp = query("SELECT SUM(value) as total FROM energy_jodi_data WHERE indicator='production' AND date=(SELECT MAX(date) FROM energy_jodi_data WHERE indicator='production')")
    jd = query("SELECT SUM(value) as total FROM energy_jodi_data WHERE indicator='demand' AND date=(SELECT MAX(date) FROM energy_jodi_data WHERE indicator='demand')")
    jodi_sig = 50.0
    if jp and jd and jp[0]["total"] and jd[0]["total"]:
        surplus = jp[0]["total"] - jd[0]["total"]
        jodi_sig = _clamp(50 - surplus/2000*50)
        ld = query("SELECT MAX(date) as d FROM energy_jodi_data WHERE indicator='production'")
        if ld and ld[0]["d"]:
            try:
                stale = (datetime.now() - datetime.strptime(ld[0]["d"], "%Y-%m")).days
                jodi_sig = 50 + (jodi_sig-50) * max(0.3, 1.0-stale/ENERGY_JODI_MAX_LAG_DAYS)
            except ValueError: pass
    ct = query("SELECT period,SUM(value_usd) as total FROM energy_trade_flows WHERE commodity_code='2709' AND trade_flow LIKE '%Import%' GROUP BY period ORDER BY period DESC LIMIT 4")
    ct_sig = 50.0
    if len(ct) >= 2 and ct[1]["total"]:
        ct_sig = _clamp(50 + ((ct[0]["total"] or 0)-(ct[1]["total"] or 0))/ct[1]["total"]*500)
    return jodi_sig*0.7 + ct_sig*0.3

def _compute_natgas_signal():
    z = _seasonal_zscore("NG.NW2_EPG0_SWO_R48_BCF.W", "macro_indicators", "indicator_id")
    return _clamp(50 - z * 16.67) if z is not None else 50.0

def _score_ticker(symbol, category, inv, prod, demand, flows, balance, natgas):
    w = ENERGY_SCORE_WEIGHTS
    base = inv*w["inventory"]+prod*w["production"]+demand*w["demand"]+flows*w["trade_flows"]+balance*w["global_balance"]
    if category == "upstream":
        return _clamp(base), f"Upstream: inv={inv:.0f} prod={prod:.0f} dem={demand:.0f} flow={flows:.0f} glob={balance:.0f}"
    elif category == "downstream":
        s = 0.4*(100-base)+0.6*demand
        return _clamp(s), f"Refiner: margin={(100-base):.0f} demand={demand:.0f}"
    elif category == "midstream":
        s = 0.5*(100-prod)+0.5*flows
        return _clamp(s), f"Midstream: vol={(100-prod):.0f} flows={flows:.0f}"
    elif category == "ofs":
        s = 0.5*(100-prod)+0.3*base+0.2*demand
        return _clamp(s), f"OFS: activity={(100-prod):.0f} crude={base:.0f}"
    elif category == "lng":
        s = 0.6*natgas+0.4*flows
        return _clamp(s), f"LNG: natgas={natgas:.0f} flows={flows:.0f}"
    return _clamp(base), f"Energy: composite={base:.0f}"

def compute_energy_intel_scores():
    rows = query("SELECT symbol,MAX(energy_intel_score) as score FROM energy_intel_signals WHERE date>=date('now','-7 days') GROUP BY symbol")
    return {r["symbol"]: r["score"] for r in rows if r["score"]}

def run():
    init_db()
    print("\n  === ENERGY INTELLIGENCE SCORING ===")
    inv = _compute_inventory_signal(); prod = _compute_production_signal()
    demand = _compute_demand_signal(); flows = _compute_trade_flow_signal()
    balance = _compute_global_balance(); natgas = _compute_natgas_signal()
    print(f"  Sub-signals: inv={inv:.1f} prod={prod:.1f} dem={demand:.1f} flow={flows:.1f} glob={balance:.1f} ng={natgas:.1f}")
    gem_scores = {}
    try:
        from tools.global_energy_markets import compute_gem_adjustments
        gem_scores = compute_gem_adjustments()
        if gem_scores: print(f"  GEM adjustments: {len(gem_scores)} tickers")
    except Exception as e: logger.warning(f"  GEM unavailable: {e}")
    today_str = date.today().isoformat(); results = []
    for category, tickers in ENERGY_INTEL_TICKERS.items():
        for symbol in tickers:
            score, narrative = _score_ticker(symbol, category, inv, prod, demand, flows, balance, natgas)
            gem = gem_scores.get(symbol)
            if gem is not None:
                orig = score; score = _clamp(score*(1-GEM_BLEND_WEIGHT)+gem*GEM_BLEND_WEIGHT)
                narrative += f" | GEM={gem:.0f} ({orig:.0f}->{score:.0f})"
            results.append((symbol, today_str, score, inv, prod, demand, flows, balance, category, narrative))
    if results:
        with get_conn() as conn:
            conn.executemany("""INSERT OR REPLACE INTO energy_intel_signals
                (symbol,date,energy_intel_score,inventory_signal,production_signal,demand_signal,
                 trade_flow_signal,global_balance_signal,ticker_category,narrative)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", results)
    scores = [r[2] for r in results]
    if scores:
        avg = sum(scores)/len(scores); above = sum(1 for s in scores if s >= 50)
        print(f"\n  {len(results)} tickers | avg={avg:.1f} | bullish={above} bearish={len(scores)-above}")
        for r in sorted(results, key=lambda r: r[2], reverse=True)[:5]:
            print(f"    {r[0]:6s} ({r[8]:10s}): {r[2]:5.1f} -- {r[9]}")
    print("  === ENERGY SCORING COMPLETE ===\n")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
