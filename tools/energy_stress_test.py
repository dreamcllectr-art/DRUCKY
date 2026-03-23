"""Energy Stress Test & Regime Detection — scenario analysis + regime classification.
Phase 2.7g: regime detection (4 dimensions) + 5 historical stress scenarios.
"""
import logging, sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
from tools.db import get_conn, init_db, query, upsert_many
logger = logging.getLogger(__name__)

DDL = [
    """CREATE TABLE IF NOT EXISTS energy_regime (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
        seasonal_regime TEXT, curve_regime TEXT, storage_regime TEXT, cot_regime TEXT,
        composite_regime TEXT, regime_score REAL, narrative TEXT, UNIQUE(date))""",
    """CREATE TABLE IF NOT EXISTS energy_stress_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, symbol TEXT NOT NULL,
        scenario TEXT NOT NULL, impact_score REAL, direction TEXT, magnitude TEXT,
        UNIQUE(date, symbol, scenario))""",
]

def _init_tables():
    conn = get_conn(); c = conn.cursor()
    for stmt in DDL: c.execute(stmt)
    conn.commit(); conn.close()

# ── REGIME DETECTION ──
def _seasonal_regime(today: Optional[date] = None) -> str:
    m = (today or date.today()).month
    if m in (11,12,1,2,3): return "winter"
    if m in (6,7,8): return "summer"
    return "shoulder_spring" if m in (4,5) else "shoulder_fall"

def _curve_regime() -> tuple[str, float]:
    rows = query("SELECT curve_id, months_out, price FROM global_energy_curves WHERE date = (SELECT MAX(date) FROM global_energy_curves) AND curve_id IN ('WTI','BRENT','HH','TTF') ORDER BY curve_id, months_out")
    if not rows: return "unknown", 0.0
    wts = {"WTI": 0.35, "BRENT": 0.35, "HH": 0.20, "TTF": 0.10}
    by_curve: dict[str, list] = {}
    for r in rows: by_curve.setdefault(r["curve_id"], []).append((r["months_out"], r["price"]))
    ws, tw = 0.0, 0.0
    for cid, pts in by_curve.items():
        if len(pts) < 2: continue
        pts.sort(key=lambda x: x[0])
        if pts[0][1] and pts[0][1] > 0:
            w = wts.get(cid, 0.1)
            ws += (pts[-1][1]-pts[0][1])/pts[0][1]*100 * w; tw += w
    spread = ws/tw if tw > 0 else 0.0
    if spread <= -3.0: label = "strong_backwardation"
    elif spread <= -0.5: label = "mild_backwardation"
    elif spread <= 2.0: label = "mild_contango"
    else: label = "strong_contango"
    return label, round(spread, 2)

def _storage_regime() -> str:
    try:
        rows = query("SELECT status FROM eu_gas_storage WHERE country = 'EU' ORDER BY date DESC LIMIT 1")
        if rows: return rows[0]["status"] or "normal"
    except Exception: pass
    try:
        rows = query("SELECT value FROM energy_eia_enhanced WHERE series_id = 'PET.WCESTUS1.W' ORDER BY date DESC LIMIT 60")
        if len(rows) >= 10:
            ratio = rows[0]["value"] / (sum(r["value"] for r in rows if r["value"]) / len(rows))
            if ratio >= 1.05: return "comfortable"
            if ratio >= 0.97: return "normal"
            return "tight" if ratio >= 0.90 else "critical"
    except Exception: pass
    return "normal"

def _cot_regime() -> str:
    try:
        rows = query("SELECT market, signal, net_percentile FROM cot_energy_positions WHERE report_date = (SELECT MAX(report_date) FROM cot_energy_positions)")
        if not rows: return "neutral"
        wts = {"WTI_CRUDE": 0.35, "BRENT": 0.25, "NAT_GAS_HH": 0.25, "RBOB": 0.15}
        ls, ss, tw = 0.0, 0.0, 0.0
        for r in rows:
            w = wts.get(r["market"], 0.0)
            if w == 0: continue
            if r["signal"] == "extreme_long": ls += w
            elif r["signal"] == "extreme_short": ss += w
            tw += w
        if tw == 0: return "neutral"
        if ls/tw >= 0.5: return "crowded_long"
        return "crowded_short" if ss/tw >= 0.5 else "neutral"
    except Exception: return "neutral"

_SCORE_MAP = {
    "winter": 60, "summer": 55, "shoulder_spring": 45, "shoulder_fall": 50,
    "strong_backwardation": 80, "mild_backwardation": 65, "mild_contango": 40, "strong_contango": 20,
    "critical": 85, "tight": 70, "normal": 50, "comfortable": 30,
    "crowded_long": 30, "neutral": 50, "crowded_short": 70,
}
_REGIME_W = {"seasonal": 0.20, "curve": 0.30, "storage": 0.30, "cot": 0.20}

def detect_regime(today: Optional[date] = None) -> dict:
    seasonal = _seasonal_regime(today)
    curve, spread_pct = _curve_regime()
    storage, cot = _storage_regime(), _cot_regime()
    scores = {"seasonal": _SCORE_MAP.get(seasonal,50), "curve": _SCORE_MAP.get(curve,50),
              "storage": _SCORE_MAP.get(storage,50), "cot": _SCORE_MAP.get(cot,50)}
    composite = sum(scores[k]*_REGIME_W[k] for k in scores)
    label = ("bullish" if composite >= 65 else "mildly_bullish" if composite >= 55
             else "neutral" if composite >= 45 else "mildly_bearish" if composite >= 35 else "bearish")
    narr = f"Seasonal={seasonal} | Curve={curve} ({spread_pct:+.1f}%) | Storage={storage} | CoT={cot} | {label} ({composite:.0f})"
    return {"seasonal": seasonal, "curve": curve, "storage": storage, "cot": cot,
            "composite": label, "score": round(composite, 1), "narrative": narr}

# ── STRESS SCENARIOS ──
SCENARIOS = {
    "russia_gas_cutoff": {"name": "Russia/Ukraine Gas Cutoff", "impacts": {"upstream":35,"midstream":20,"downstream":-20,"ofs":25,"lng":85,"utility":-65,"clean_energy":40}},
    "texas_winter_storm": {"name": "Texas Winter Storm Uri", "impacts": {"upstream":-40,"midstream":-55,"downstream":-15,"ofs":-10,"lng":30,"utility":-50,"clean_energy":-5}},
    "covid_demand_collapse": {"name": "COVID Demand Collapse", "impacts": {"upstream":-80,"midstream":-40,"downstream":-60,"ofs":-70,"lng":-30,"utility":10,"clean_energy":15}},
    "aramco_attack": {"name": "Saudi Aramco Abqaiq Attack", "impacts": {"upstream":40,"midstream":10,"downstream":-25,"ofs":30,"lng":15,"utility":-10,"clean_energy":20}},
    "lng_supply_tightness": {"name": "2018 LNG Supply Tightness", "impacts": {"upstream":15,"midstream":10,"downstream":-5,"ofs":20,"lng":75,"utility":-20,"clean_energy":10}},
}
CATEGORY_TICKERS = {
    "upstream": ["OXY","COP","XOM","CVX","DVN","FANG","EOG","APA","MRO"],
    "midstream": ["ET","WMB","KMI","OKE","TRGP"], "downstream": ["MPC","VLO","PSX"],
    "ofs": ["SLB","HAL","BKR"], "lng": ["LNG","TELL"],
    "utility": ["VST","CEG","NRG","NEE","DUK","SO","AEP","XEL","D","EIX"],
    "clean_energy": ["ENPH","FSLR","NEE","BEP","PLUG","BE","SEDG","ARRY"],
}
TICKER_MODIFIERS = {
    "LNG": {"russia_gas_cutoff":10,"lng_supply_tightness":10}, "TELL": {"russia_gas_cutoff":5,"lng_supply_tightness":5},
    "ET": {"texas_winter_storm":-20}, "APA": {"covid_demand_collapse":-10},
    "DVN": {"covid_demand_collapse":-10}, "NEE": {"russia_gas_cutoff":15,"texas_winter_storm":-10},
}

def compute_stress_scores(today_str: str) -> list[tuple]:
    records = []
    for sid, sc in SCENARIOS.items():
        for cat, tickers in CATEGORY_TICKERS.items():
            base = sc["impacts"].get(cat, 0)
            for sym in tickers:
                raw = max(-100, min(100, base + TICKER_MODIFIERS.get(sym, {}).get(sid, 0)))
                direction = "beneficiary" if raw >= 20 else ("vulnerable" if raw <= -20 else "neutral")
                a = abs(raw)
                mag = "extreme" if a >= 60 else ("high" if a >= 35 else ("moderate" if a >= 15 else "low"))
                records.append((today_str, sym, sid, float(raw), direction, mag))
    return records

def _persist(records, regime, today_str):
    upsert_many("energy_stress_scores",
        ["date", "symbol", "scenario", "impact_score", "direction", "magnitude"],
        records)
    upsert_many("energy_regime",
        ["date", "seasonal_regime", "curve_regime", "storage_regime", "cot_regime",
         "composite_regime", "regime_score", "narrative"],
        [(today_str, regime["seasonal"], regime["curve"], regime["storage"],
          regime["cot"], regime["composite"], regime["score"], regime["narrative"])])

def get_regime_adjustment(symbol: str, category: str) -> float:
    rows = query("SELECT composite_regime FROM energy_regime WHERE date >= date('now','-3 days') ORDER BY date DESC LIMIT 1")
    if not rows: return 1.0
    return {"bullish":1.25,"mildly_bullish":1.10,"neutral":1.00,"mildly_bearish":0.90,"bearish":0.75}.get(rows[0]["composite_regime"] or "neutral", 1.0)

def get_stress_vulnerability(symbol: str) -> dict:
    rows = query("SELECT scenario, impact_score, direction, magnitude FROM energy_stress_scores WHERE symbol = ? AND date >= date('now','-7 days') ORDER BY impact_score", [symbol])
    if not rows: return {"worst": None, "best": None, "vulnerabilities": []}
    mk = lambda r: {"scenario": r["scenario"], "impact": r["impact_score"], "magnitude": r["magnitude"]}
    return {"worst": mk(rows[0]), "best": mk(rows[-1]),
            "vulnerabilities": [{"scenario": r["scenario"], "impact": r["impact_score"]} for r in rows if r["direction"] == "vulnerable"]}

def run():
    init_db(); _init_tables()
    today_str = date.today().isoformat()
    print("\n  === ENERGY REGIME & STRESS ANALYSIS ===")
    regime = detect_regime()
    print(f"  {regime['narrative']}")
    n_tickers = sum(len(t) for t in CATEGORY_TICKERS.values())
    print(f"\n  Running 5 stress scenarios across {n_tickers} tickers...")
    records = compute_stress_scores(today_str)
    _persist(records, regime, today_str)
    print(f"  {len(records)} stress records saved")
    print(f"\n  Scenario Vulnerability Summary:")
    for sid, sc in SCENARIOS.items():
        vuln = sorted([(r[1],r[3]) for r in records if r[2]==sid and r[3]<=-35], key=lambda x: x[1])
        bene = sorted([(r[1],r[3]) for r in records if r[2]==sid and r[3]>=35], key=lambda x: x[1], reverse=True)
        print(f"    {sc['name'][:30]:30s}  + {', '.join(f'{s}({v:+.0f})' for s,v in bene[:5])[:35]:<35}  - {', '.join(f'{s}({v:+.0f})' for s,v in vuln[:5])[:35]}")
    print("  === ENERGY STRESS COMPLETE ===\n")
    return {"regime": regime["composite"], "stress_records": len(records)}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
