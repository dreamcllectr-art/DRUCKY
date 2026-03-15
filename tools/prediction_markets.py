"""Prediction Markets — Polymarket probabilities -> stock signals.
Fetches markets, classifies via Gemini, maps to sector/stock impacts, scores 0-100.
"""
import sys, json, math, time, logging
from datetime import date
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import (GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    PM_MIN_VOLUME, PM_MIN_LIQUIDITY, PM_CLASSIFICATION_BATCH_SIZE,
    PM_GEMINI_DELAY, PM_FETCH_LIMIT, PM_LOOKBACK_DAYS)
from tools.db import init_db, upsert_many, query
logger = logging.getLogger(__name__)
GAMMA_API = "https://gamma-api.polymarket.com"

CATEGORY_IMPACTS = {
    "fed_rate_cut":       {"bullish":["Technology","Consumer Discretionary","Real Estate","Communication Services"],"bearish":["Financials"],"symbols_bullish":[],"symbols_bearish":[]},
    "fed_rate_hike":      {"bullish":["Financials","Energy"],"bearish":["Technology","Consumer Discretionary","Real Estate"],"symbols_bullish":[],"symbols_bearish":[]},
    "inflation_higher":   {"bullish":["Energy","Materials","Real Estate"],"bearish":["Technology","Consumer Discretionary","Utilities"],"symbols_bullish":["GLD","XOM","CVX"],"symbols_bearish":[]},
    "inflation_lower":    {"bullish":["Technology","Consumer Discretionary"],"bearish":["Energy","Materials"],"symbols_bullish":[],"symbols_bearish":[]},
    "tariff_increase":    {"bullish":["Utilities","Consumer Staples"],"bearish":["Technology","Industrials","Materials","Consumer Discretionary"],"symbols_bullish":[],"symbols_bearish":["AAPL","TSLA","NKE","CAT"]},
    "tariff_decrease":    {"bullish":["Technology","Industrials","Materials"],"bearish":["Utilities"],"symbols_bullish":["AAPL","TSLA","NKE","CAT"],"symbols_bearish":[]},
    "recession_risk":     {"bullish":["Utilities","Consumer Staples","Health Care"],"bearish":["Consumer Discretionary","Financials","Industrials","Materials","Energy"],"symbols_bullish":["GLD"],"symbols_bearish":[]},
    "government_spending_increase": {"bullish":["Industrials","Materials","Health Care"],"bearish":[],"symbols_bullish":["LMT","RTX","NOC","GD"],"symbols_bearish":[]},
    "tech_regulation":    {"bullish":[],"bearish":["Technology","Communication Services"],"symbols_bullish":[],"symbols_bearish":["GOOGL","META","AMZN","AAPL","MSFT"]},
    "energy_policy_green":{"bullish":["Utilities"],"bearish":["Energy"],"symbols_bullish":["ENPH","FSLR","NEE"],"symbols_bearish":["XOM","CVX","COP"]},
    "energy_policy_fossil":{"bullish":["Energy"],"bearish":[],"symbols_bullish":["XOM","CVX","COP","OXY"],"symbols_bearish":["ENPH","FSLR"]},
    "geopolitical_escalation":{"bullish":["Energy","Utilities","Consumer Staples"],"bearish":["Technology","Consumer Discretionary","Financials"],"symbols_bullish":["LMT","RTX","NOC","GLD"],"symbols_bearish":[]},
    "china_slowdown":     {"bullish":["Utilities","Consumer Staples"],"bearish":["Materials","Industrials","Energy"],"symbols_bullish":[],"symbols_bearish":["CAT","DE","FCX","NEM"]},
    "crypto_regulation_positive":{"bullish":["Financials"],"bearish":[],"symbols_bullish":["COIN","MSTR","SQ"],"symbols_bearish":[]},
}

def _fetch_active_markets():
    markets, offset = [], 0
    while len(markets) < PM_FETCH_LIMIT:
        try:
            resp = requests.get(f"{GAMMA_API}/markets", params={"active":"true","closed":"false","limit":100,"offset":offset}, timeout=15)
            resp.raise_for_status(); batch = resp.json()
            if not batch: break
            for m in batch:
                vol, liq = float(m.get("volumeNum",0) or 0), float(m.get("liquidityNum",0) or 0)
                if vol < PM_MIN_VOLUME or liq < PM_MIN_LIQUIDITY: continue
                try: op = json.loads(m.get("outcomePrices","[]"))
                except: op = []
                yp = float(op[0]) if op else None
                if yp is None: continue
                markets.append({"id":m.get("conditionId",m.get("id","")),"question":m.get("question",""),"category":m.get("category",""),
                    "yes_probability":yp,"no_probability":1-yp,"volume":vol,"liquidity":liq,"end_date":m.get("endDate",""),
                    "description":(m.get("description","") or "")[:500],"volume_24h":float(m.get("volume24hr",0) or 0)})
            offset += 100; time.sleep(0.3)
        except requests.RequestException as e: logger.warning(f"Polymarket error: {e}"); break
    return markets

def _classify_markets_batch(markets):
    if not GEMINI_API_KEY: return []
    cats = list(CATEGORY_IMPACTS.keys()); classified = []
    for i in range(0, len(markets), PM_CLASSIFICATION_BATCH_SIZE):
        batch = markets[i:i+PM_CLASSIFICATION_BATCH_SIZE]
        texts = [f'{j+1}. Q: "{m["question"]}" | YES={m["yes_probability"]:.0%} | Vol=${m["volume"]:,.0f} | Cat: {m["category"]} | Ends: {m["end_date"][:10] if m["end_date"] else "N/A"}' for j,m in enumerate(batch)]
        prompt = f"""Macro strategist classifying prediction markets for stock impact.
Skip sports/entertainment. Categories: {json.dumps(cats)}
For each, respond JSON array: [{{"index":<1-based>,"is_relevant":bool,"impact_category":"<cat or null>","direction":"yes_bullish"|"yes_bearish","confidence":<0-100>,"specific_symbols":["TICKER"],"rationale":"<1 sentence>"}}]
Markets:\n{chr(10).join(texts)}\nRespond ONLY with JSON array."""
        try:
            resp = requests.post(f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
                headers={"Content-Type":"application/json"},params={"key":GEMINI_API_KEY},
                json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.2,"maxOutputTokens":2048}},timeout=30)
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text.startswith("```"): text = text.split("\n",1)[1].rsplit("```",1)[0].strip()
            for cls in json.loads(text):
                idx = cls.get("index",0)-1
                if 0<=idx<len(batch) and cls.get("is_relevant"):
                    m = batch[idx].copy()
                    m.update({"impact_category":cls.get("impact_category"),"direction":cls.get("direction","yes_bullish"),
                        "confidence":cls.get("confidence",50),"specific_symbols":cls.get("specific_symbols",[]),"rationale":cls.get("rationale","")})
                    classified.append(m)
        except Exception as e: logger.warning(f"Gemini batch error: {e}")
        time.sleep(PM_GEMINI_DELAY)
    return classified

def _compute_symbol_scores(classified):
    sector_map = {r["symbol"]:r["sector"] for r in query("SELECT symbol,sector FROM stock_universe WHERE symbol IS NOT NULL AND sector IS NOT NULL")}
    sym_sigs: dict[str,list] = {}
    for mkt in classified:
        cat = mkt.get("impact_category")
        if not cat or cat not in CATEGORY_IMPACTS: continue
        imp = CATEGORY_IMPACTS[cat]
        prob, direction = mkt["yes_probability"], mkt.get("direction","yes_bullish")
        conf = mkt.get("confidence",50)/100.0
        ep = prob if direction=="yes_bullish" else 1-prob
        vf = min(2.0, max(0.5, math.log10(max(mkt["volume"],1000))-3.0))
        ss = ep*conf*vf
        info = {"question":mkt["question"][:100],"category":cat,"probability":prob,"direction":direction,"strength":ss}
        for sym, sec in sector_map.items():
            impact = 0.0
            if sec in imp.get("bullish",[]): impact = ss*0.6
            elif sec in imp.get("bearish",[]): impact = -ss*0.6
            if sym in imp.get("symbols_bullish",[]): impact += ss*0.9
            elif sym in imp.get("symbols_bearish",[]): impact -= ss*0.9
            if sym in mkt.get("specific_symbols",[]): impact += ss*0.8 if direction=="yes_bullish" else -ss*0.8
            if abs(impact)>0.01: sym_sigs.setdefault(sym,[]).append({**info,"impact":impact})
    results = {}
    for sym, sigs in sym_sigs.items():
        ni = sum(s["impact"] for s in sigs)
        mc = len(sigs)
        score = max(0, min(100, (ni/2+1)/2*100 * min(1.5, 1+(mc-1)*0.1)))
        if abs(score-50)>5: results[sym] = {"score":round(score,2),"signals":sigs[:5],"market_count":mc,"net_impact":round(ni,4)}
    return results

def compute_prediction_market_scores():
    rows = query(f"SELECT symbol,MAX(pm_score) as score FROM prediction_market_signals WHERE date>=date('now','-{PM_LOOKBACK_DAYS} days') AND status='active' GROUP BY symbol")
    return {r["symbol"]:r["score"] for r in rows if r["score"]}

def run():
    init_db(); today = date.today().isoformat()
    print("\n"+"="*60+"\n  PREDICTION MARKETS MODULE (Polymarket)\n"+"="*60)
    print("\n  Step 1: Fetching markets...")
    markets = _fetch_active_markets()
    if not markets: print("  No markets found"); return
    print(f"  {len(markets)} markets above thresholds")
    print("\n  Step 2: Classifying...")
    classified = _classify_markets_batch(markets)
    if not classified: print("  No relevant markets"); return
    print(f"\n  RELEVANT ({len(classified)}):")
    print(f"  {'Question':<55} {'YES%':>5} {'Category':<24} {'Vol':>10}")
    for m in sorted(classified, key=lambda x: x["volume"], reverse=True)[:15]:
        print(f"  {m['question'][:54]:<55} {m['yes_probability']:>4.0%} {m.get('impact_category',''):<24} ${m['volume']:>9,.0f}")
    print("\n  Step 3: Scoring symbols...")
    sym_scores = _compute_symbol_scores(classified)
    if not sym_scores: print("  No scores"); return
    rows = []
    for sym, d in sym_scores.items():
        top = sorted(d["signals"], key=lambda s: abs(s["impact"]), reverse=True)[:3]
        narr = "; ".join(f"{s['question'][:60]} ({s['probability']:.0%} -> {'supports' if s['impact']>0 else 'pressures'})" for s in top)
        rows.append((sym,today,round(d["score"],2),d["market_count"],round(d["net_impact"],4),"active",narr[:500]))
    if rows: upsert_many("prediction_market_signals",["symbol","date","pm_score","market_count","net_impact","status","narrative"],rows)
    mkt_rows = [(m["id"][:64],today,m["question"][:300],m.get("impact_category",""),round(m["yes_probability"],4),
        round(m["volume"],2),round(m["liquidity"],2),m.get("direction","yes_bullish"),m.get("confidence",50),
        json.dumps(m.get("specific_symbols",[])),m.get("rationale","")[:300],m.get("end_date","")[:10]) for m in classified]
    if mkt_rows: upsert_many("prediction_market_raw",["market_id","date","question","impact_category","yes_probability","volume","liquidity","direction","confidence","specific_symbols","rationale","end_date"],mkt_rows)
    bull = sum(1 for d in sym_scores.values() if d["score"]>55)
    bear = sum(1 for d in sym_scores.values() if d["score"]<45)
    print(f"\n  Results: {len(sym_scores)} symbols | Bullish:{bull} Neutral:{len(sym_scores)-bull-bear} Bearish:{bear}")
    for label, filt, rev in [("BULLISH",lambda d:d["score"]>55,True),("BEARISH",lambda d:d["score"]<45,False)]:
        top = sorted([(s,d) for s,d in sym_scores.items() if filt(d)], key=lambda x:x[1]["score"], reverse=rev)[:10]
        if top:
            print(f"\n  TOP {label}:")
            print(f"  {'Sym':<8} {'Score':>6} {'Mkts':>6} {'Impact':>10}")
            for s,d in top: print(f"  {s:<8} {d['score']:>6.1f} {d['market_count']:>6} {d['net_impact']:>+10.3f}")
    print(f"\nPrediction Markets: {len(rows)} signals persisted\n"+"="*60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
