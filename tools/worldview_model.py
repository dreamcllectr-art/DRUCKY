"""Macro Worldview Model — translates macro regime into stock expressions via thesis alignment."""
import sys, json, logging, time
from datetime import date
from pathlib import Path
logger = logging.getLogger(__name__)
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL
from tools.db import init_db, upsert_many, query

THESIS_DEFINITIONS = {
    "tight_money": {"trigger": lambda s: s.get("fed_funds_score",0)<-5 and s.get("real_rates_score",0)<-3,
        "bullish_sectors": ["Financials","Energy"], "bearish_sectors": ["Technology","Consumer Discretionary","Real Estate","Communication Services"],
        "tagged_symbols": [], "description": "Fed tightening + rising real rates: value over growth"},
    "easy_money": {"trigger": lambda s: s.get("fed_funds_score",0)>5 and s.get("m2_score",0)>3,
        "bullish_sectors": ["Technology","Consumer Discretionary","Communication Services","Real Estate"],
        "bearish_sectors": ["Financials"], "tagged_symbols": [], "description": "Fed cutting + M2 expanding: risk-on, growth wins"},
    "strong_dollar": {"trigger": lambda s: s.get("dxy_score",0)<-5,
        "bullish_sectors": ["Utilities","Consumer Staples","Health Care"], "bearish_sectors": ["Materials","Energy","Industrials"],
        "tagged_symbols": [], "description": "Strong USD: domestic defensives win"},
    "weak_dollar": {"trigger": lambda s: s.get("dxy_score",0)>5,
        "bullish_sectors": ["Materials","Energy","Industrials"], "bearish_sectors": ["Consumer Staples","Utilities"],
        "tagged_symbols": [], "description": "Weak USD: commodity producers and multinationals win"},
    "credit_stress": {"trigger": lambda s: s.get("credit_spreads_score",0)<-5,
        "bullish_sectors": ["Utilities","Consumer Staples","Health Care"], "bearish_sectors": ["Financials","Real Estate","Consumer Discretionary","Industrials"],
        "tagged_symbols": [], "description": "Credit stress: defensives outperform"},
    "steepening_curve": {"trigger": lambda s: s.get("yield_curve_score",0)>8,
        "bullish_sectors": ["Financials"], "bearish_sectors": ["Utilities","Real Estate"],
        "tagged_symbols": [], "description": "Steepening curve: bank NIM expansion"},
    "risk_off": {"trigger": lambda s: s.get("vix_score",0)<-8 and s.get("total_score",0)<-20,
        "bullish_sectors": ["Utilities","Consumer Staples","Health Care"], "bearish_sectors": ["Technology","Consumer Discretionary","Materials","Energy","Industrials"],
        "tagged_symbols": ["GLD","GC=F"], "description": "Risk-off: defensives and gold win"},
    "ai_capex_supercycle": {"trigger": lambda s: s.get("research_ai_capex_score",0)>50,
        "bullish_sectors": ["Technology","Communication Services"], "bearish_sectors": [],
        "tagged_symbols": ["NVDA","AMD","TSM","AVGO","MSFT","GOOGL","META","AMZN","ORCL","AMAT","LRCX","ASML"],
        "description": "AI compute capex cycle: semis and hyperscalers"},
    "em_slowdown": {"trigger": lambda s: s.get("em_gdp_trend",0)<-1.0,
        "bullish_sectors": ["Utilities","Consumer Staples","Health Care"], "bearish_sectors": ["Materials","Industrials","Energy"],
        "tagged_symbols": [], "description": "EM growth decelerating: defensives win"},
    "global_trade_contraction": {"trigger": lambda s: s.get("global_trade_trend",0)<-2.0,
        "bullish_sectors": ["Utilities","Consumer Staples"], "bearish_sectors": ["Industrials","Materials","Technology"],
        "tagged_symbols": [], "description": "Global trade contracting"},
    "sovereign_risk": {"trigger": lambda s: s.get("sovereign_debt_stress",0)>1.5,
        "bullish_sectors": ["Utilities","Consumer Staples","Health Care"], "bearish_sectors": ["Financials","Real Estate"],
        "tagged_symbols": ["GLD"], "description": "Sovereign debt stress: flight to quality"},
    "capital_rotation_to_dm": {"trigger": lambda s: s.get("dm_gdp_advantage",0)>1.5 and s.get("dxy_score",0)<-3,
        "bullish_sectors": ["Technology","Health Care","Financials"], "bearish_sectors": ["Materials"],
        "tagged_symbols": [], "description": "Capital rotating EM to DM: US quality benefits"},
}
BULLISH_SECTOR_TILT, BEARISH_SECTOR_TILT = +0.35, -0.35
TAGGED_SYMBOL_TILT, NARRATIVE_TOP_N = +0.55, 20
_EM_WB, _DM_WB = "CHN;IND;BRA;IDN;MEX;TUR;THA;ZAF", "USA;GBR;DEU;JPN;FRA;CAN"

def _fetch_wb(indicator, countries, years=5):
    import datetime as _dt
    end_year = _dt.datetime.now().year
    try:
        resp = requests.get(f"https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}?date={end_year-years}:{end_year}&format=json&per_page=500", timeout=15)
        resp.raise_for_status(); data = resp.json()
        if not isinstance(data, list) or len(data) < 2 or not data[1]: return []
        return [{"country": r["countryiso3code"], "year": int(r["date"]), "value": r["value"]} for r in data[1] if r.get("value") is not None]
    except Exception as e: logger.warning(f"WB API error ({indicator}): {e}"); return []

def _yearly_avg(data):
    by_year = {}
    for r in data: by_year.setdefault(r["year"], []).append(r["value"])
    return {y: sum(v)/len(v) for y, v in by_year.items() if v}

def _compute_global_macro_scores():
    scores = {"em_gdp_trend": 0.0, "global_trade_trend": 0.0, "sovereign_debt_stress": 0.0, "dm_gdp_advantage": 0.0}
    em_gdp = _fetch_wb("NY.GDP.MKTP.KD.ZG", _EM_WB)
    if em_gdp:
        ya = _yearly_avg(em_gdp); sy = sorted(ya.keys())
        if len(sy) >= 3: scores["em_gdp_trend"] = ya.get(sy[-1], 0) - sum(ya[y] for y in sy[-4:-1]) / 3
    trade = _fetch_wb("NE.TRD.GNFS.ZS", f"{_EM_WB};{_DM_WB}")
    if trade:
        ya = _yearly_avg(trade); sy = sorted(ya.keys())
        if len(sy) >= 2: scores["global_trade_trend"] = ya[sy[-1]] - ya[sy[-2]]
    debt = _fetch_wb("GC.DOD.TOTL.GD.ZS", _DM_WB)
    if debt:
        ya = _yearly_avg(debt); sy = sorted(ya.keys())
        if len(sy) >= 2: scores["sovereign_debt_stress"] = (ya[sy[-1]] - ya[sy[-2]]) / 10.0
    try:
        import datetime as _dt
        years = ",".join(str(_dt.datetime.now().year + i) for i in range(3))
        resp = requests.get(f"https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH?periods={years}", timeout=15)
        resp.raise_for_status(); values = resp.json().get("values", {}).get("NGDP_RPCH", {})
        ny = _dt.datetime.now().year + 1
        em_f = [values[c].get(str(ny), 0) for c in ["CHN","IND","BRA","IDN","MEX","TUR"] if c in values]
        dm_f = [values[c].get(str(ny), 0) for c in ["USA","GBR","DEU","JPN","FRA","CAN"] if c in values]
        if em_f and dm_f: scores["dm_gdp_advantage"] = sum(dm_f)/len(dm_f) - sum(em_f)/len(em_f) + 3.0
    except Exception: pass
    return scores

def _get_active_theses(macro_scores):
    aug = dict(macro_scores)
    rows = query("SELECT AVG(relevance_score) as avg_score FROM research_signals WHERE source IN ('epoch_ai','semianalysis') AND date >= date('now','-14 days') AND symbol IS NULL")
    aug["research_ai_capex_score"] = float(rows[0]["avg_score"]) if rows and rows[0]["avg_score"] is not None else 0.0
    try:
        gs = _compute_global_macro_scores(); aug.update(gs)
        if any(v != 0 for v in gs.values()): print(f"  Global macro: " + ", ".join(f"{k}={v:+.2f}" for k, v in gs.items() if v != 0))
    except Exception as e: logger.warning(f"Global macro unavailable: {e}")
    active = []
    for key, thesis in THESIS_DEFINITIONS.items():
        try:
            if thesis["trigger"](aug): active.append(key)
        except Exception: pass
    return active

def run():
    init_db(); today = date.today().isoformat()
    print("Worldview Model: Translating macro thesis to stock expression...")
    ms = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    if not ms: print("  Warning: No macro scores found"); return
    ms = dict(ms[0]); regime = ms.get("regime", "neutral")
    print(f"  Current regime: {regime} (score: {float(ms.get('total_score') or 0):.1f})")
    active_theses = _get_active_theses(ms)
    if active_theses:
        print(f"  Active theses ({len(active_theses)}): {', '.join(active_theses)}")
        for t in active_theses: print(f"    -> {THESIS_DEFINITIONS[t]['description']}")
    else: print("  No strong macro theses active")
    stock_scores = query("SELECT u.symbol, u.sector, COALESCE(t.total_score, 50) as tech_score, COALESCE(f.total_score, 50) as fund_score FROM stock_universe u LEFT JOIN (SELECT symbol, total_score FROM technical_scores WHERE date = (SELECT MAX(date) FROM technical_scores WHERE symbol = technical_scores.symbol)) t ON u.symbol = t.symbol LEFT JOIN (SELECT symbol, total_score FROM fundamental_scores WHERE date = (SELECT MAX(date) FROM fundamental_scores WHERE symbol = fundamental_scores.symbol)) f ON u.symbol = f.symbol")
    if not stock_scores: print("  Warning: No stock scores found"); return
    print(f"  Scoring {len(stock_scores)} stocks...")
    results = []
    for row in stock_scores:
        symbol, sector = row["symbol"], row["sector"] or "Unknown"
        tilt = 0.0
        for tk in active_theses:
            td = THESIS_DEFINITIONS[tk]
            if symbol in td.get("tagged_symbols",[]): tilt += TAGGED_SYMBOL_TILT
            elif sector in td.get("bullish_sectors",[]): tilt += BULLISH_SECTOR_TILT
            elif sector in td.get("bearish_sectors",[]): tilt += BEARISH_SECTOR_TILT
        tilt = max(-1.0, min(1.0, tilt))
        score = ((tilt+1.0)/2.0*100.0)*0.50 + (row["tech_score"] or 50.0)*0.30 + (row["fund_score"] or 50.0)*0.20
        results.append({"symbol": symbol, "sector": sector, "sector_tilt": tilt, "score": score})
    results.sort(key=lambda x: x["score"], reverse=True)
    top_syms = {r["symbol"] for r in results[:NARRATIVE_TOP_N] if r["sector_tilt"] > 0.2}
    rows, nc = [], 0
    for rank, r in enumerate(results, 1):
        st = [t for t in active_theses if r["symbol"] in THESIS_DEFINITIONS[t].get("tagged_symbols",[]) or r["sector"] in THESIS_DEFINITIONS[t].get("bullish_sectors",[]) or r["sector"] in THESIS_DEFINITIONS[t].get("bearish_sectors",[])]
        if r["symbol"] in top_syms and GEMINI_API_KEY and nc < 15:
            descs = "; ".join(THESIS_DEFINITIONS[t]["description"] for t in st if t in THESIS_DEFINITIONS)
            try:
                resp = requests.post(f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
                    headers={"Content-Type": "application/json"}, params={"key": GEMINI_API_KEY},
                    json={"contents": [{"parts": [{"text": f"In one sentence (<160 chars), explain why {r['symbol']} ({r['sector']}) expresses: {descs}. Speak like Druckenmiller."}]}],
                        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 128}}, timeout=15)
                resp.raise_for_status(); narr = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()[:200]
            except Exception: narr = f"{r['symbol']} ({r['sector']}): {', '.join(st[:2])} thesis. Score {r['score']:.0f}/100."
            nc += 1; time.sleep(0.3)
        else:
            ts = " + ".join(t.replace("_"," ") for t in st[:2])
            narr = f"{r['symbol']} ({r['sector']}): {'best expression of '+ts if ts else 'no active thesis'}. Score {r['score']:.0f}/100."
        rows.append((r["symbol"], today, regime, round(r["score"],2), round(r["sector_tilt"],4), rank, json.dumps(st), narr))
    if rows: upsert_many("worldview_signals", ["symbol","date","regime","thesis_alignment_score","sector_tilt","macro_expression_rank","active_theses","narrative"], rows)
    top = [r for r in results[:20] if r["sector_tilt"] > 0.1]
    print(f"\n  TOP WORLDVIEW EXPRESSIONS (regime: {regime}):")
    for r in top[:12]:
        at = [t[:12] for t in active_theses if r["symbol"] in THESIS_DEFINITIONS[t].get("tagged_symbols",[]) or r["sector"] in THESIS_DEFINITIONS[t].get("bullish_sectors",[])]
        print(f"  {r['symbol']:<8} {r['sector'][:25]:<26} {r['score']:>6.1f} {r['sector_tilt']:>+5.2f}  {', '.join(at[:2]) or '-'}")
    print(f"\nWorldview complete: {len(rows)} scored, {nc} LLM narratives")

if __name__ == "__main__": run()
