"""M&A Intelligence Module — acquisition target scoring + rumor detection."""
import json, logging, math, re, time
from datetime import date, datetime, timedelta
import finnhub, requests
from tools.db import get_conn, query, upsert_many, init_db
from tools.config import (
    FINNHUB_API_KEY, SERPER_API_KEY, GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    MA_RUMOR_LOOKBACK_DAYS, MA_RUMOR_HALF_LIFE_DAYS, MA_NEWS_BATCH_SIZE,
    MA_FINNHUB_DELAY, MA_GEMINI_DELAY, MA_MIN_MARKET_CAP, MA_MAX_MARKET_CAP,
    MA_TARGET_WEIGHT_PROFILE, MA_TARGET_WEIGHT_RUMOR, MA_MIN_SCORE_STORE,
)
logger = logging.getLogger(__name__)

SECTOR_MA_BASE_RATES = {
    "Technology": 1.40, "Healthcare": 1.35, "Communication Services": 1.20,
    "Financials": 1.15, "Energy": 1.10, "Industrials": 1.00,
    "Consumer Discretionary": 0.95, "Consumer Staples": 0.90, "Materials": 0.90,
    "Real Estate": 0.85, "Utilities": 0.80,
}
MCAP_ATTR = [(0,2e9,0.4),(2e9,10e9,1.0),(10e9,30e9,0.9),(30e9,100e9,0.5),(100e9,1e15,0.2)]
MA_KW = {"consolidation","merger","acquisition","buyout","takeover","strategic review",
    "activist","spin-off","spinoff","divestiture","going private","leveraged buyout","lbo","m&a"}
MA_KW_NEWS = {"acqui","merger","buyout","takeover","bid","offer","going private",
    "strategic review","strategic alternative","deal","consortium","approach","proposal",
    "activist","spin-off","divest"}
STAGE_MULT = {"speculation":0.30,"rumor":0.60,"confirmed_interest":0.85,
    "definitive_agreement":1.00,"completed":0.10,"denied":0.15}

def _load_universe():
    return query("SELECT u.symbol,u.sector,f.value as market_cap,u.name as company_name "
        "FROM stock_universe u INNER JOIN fundamentals f ON f.symbol=u.symbol AND f.metric='marketCap' "
        "WHERE u.sector IS NOT NULL AND f.value IS NOT NULL AND f.value>0")

def _load_fundamentals():
    rows = query("SELECT symbol,metric,value FROM fundamentals WHERE metric IN "
        "('trailingPE','forwardPE','priceToBook','priceToSales','enterpriseToEbitda',"
        "'debt_equity','current_ratio','profit_margin','operating_margin','roe','roa',"
        "'revenue_growth','earnings_growth','dividend_yield','analyst_target_consensus')")
    r = {}
    for row in rows: r.setdefault(row["symbol"], {})[row["metric"]] = row["value"]
    return r

def _load_smart_money():
    return {r["symbol"]: dict(r) for r in query("SELECT s.symbol,s.conviction_score,s.manager_count,s.top_holders "
        "FROM smart_money_scores s INNER JOIN (SELECT symbol,MAX(date) as mx FROM smart_money_scores "
        "GROUP BY symbol) m ON s.symbol=m.symbol AND s.date=m.mx")}

def _load_13f_accum():
    rows = query("SELECT symbol,action,market_value,portfolio_pct,manager_name FROM filings_13f WHERE period_of_report>=date('now','-6 months')")
    acc = {}
    for r in rows:
        sym = r["symbol"]
        if sym not in acc: acc[sym] = {"np": 0, "tiv": 0.0, "mpp": 0.0, "mgrs": set()}
        if r["action"] in ("new","NEW"): acc[sym]["np"] += 1
        if r["action"] in ("increase","INCREASE","new","NEW"): acc[sym]["tiv"] += (r["market_value"] or 0)
        pct = r["portfolio_pct"] or 0
        if pct > acc[sym]["mpp"]: acc[sym]["mpp"] = pct
        acc[sym]["mgrs"].add(r["manager_name"])
    for sym in acc: acc[sym]["ua"] = len(acc[sym].pop("mgrs"))
    return acc

def _load_insider_signals():
    return {r["symbol"]: dict(r) for r in query("SELECT s.symbol,s.insider_score,s.cluster_buy,"
        "s.cluster_count,s.total_buy_value_30d FROM insider_signals s "
        "INNER JOIN (SELECT symbol,MAX(date) as mx FROM insider_signals GROUP BY symbol) m "
        "ON s.symbol=m.symbol AND s.date=m.mx")}

def _sv(f):
    s,c = 0.0,0
    ev = f.get("enterpriseToEbitda")
    if ev and ev>0: c+=2; s+=(100 if ev<8 else 75 if ev<12 else 40 if ev<18 else 10)*2
    pb = f.get("priceToBook")
    if pb and pb>0: c+=1; s+=90 if pb<1.5 else 60 if pb<3 else 30 if pb<5 else 10
    fpe = f.get("forwardPE")
    if fpe and fpe>0: c+=1; s+=85 if fpe<12 else 60 if fpe<18 else 35 if fpe<25 else 10
    tpe = f.get("trailingPE")
    if f.get("analyst_target_consensus") and tpe and tpe>0 and fpe and fpe<tpe*0.85: c+=1; s+=70
    return (s/c) if c else 0.0

def _sb(f):
    s,c = 0.0,0
    de = f.get("debt_equity")
    if de is not None: c+=2; s+=(100 if de<30 else 75 if de<80 else 40 if de<150 else 15 if de<300 else 0)*2
    opm = f.get("operating_margin")
    if opm is not None: c+=1; s+=90 if opm>0.25 else 70 if opm>0.15 else 45 if opm>0.08 else 20 if opm>0 else 5
    cr = f.get("current_ratio")
    if cr is not None: c+=1; s+=80 if cr>2.0 else 65 if cr>1.5 else 40 if cr>1.0 else 10
    roe = f.get("roe")
    if roe is not None: c+=1; s+=90 if roe>0.20 else 65 if roe>0.12 else 35 if roe>0.05 else 10
    return (s/c) if c else 0.0

def _sg(f):
    s,c = 0.0,0
    rg = f.get("revenue_growth")
    if rg is not None: c+=1; s+=95 if rg>0.30 else 80 if rg>0.15 else 55 if rg>0.05 else 35 if rg>0 else 15
    eg = f.get("earnings_growth")
    if eg is not None: c+=1; s+=90 if eg>0.25 else 70 if eg>0.10 else 45 if eg>0 else 15
    return (s/c) if c else 0.0

def _ssm(sym, sm, acc, ins):
    s,w = 0.0,0.0
    a = acc.get(sym)
    if a:
        s+=(90 if a["np"]>=4 else 65 if a["np"]>=2 else 35 if a["np"]>=1 else 0)*0.30; w+=0.30
        s+=(95 if a["mpp"]>10 else 70 if a["mpp"]>5 else 40 if a["mpp"]>2 else 0)*0.25; w+=0.25
        s+=(85 if a["ua"]>=5 else 55 if a["ua"]>=3 else 0)*0.15; w+=0.15
    m = sm.get(sym)
    if m: s+=(m.get("conviction_score",0) or 0)*0.15; w+=0.15
    i = ins.get(sym)
    if i:
        if i.get("cluster_buy"): s+=(95 if (i.get("cluster_count",0) or 0)>=3 else 75)*0.15
        else:
            bv = i.get("total_buy_value_30d",0) or 0
            s+=(50 if bv>1e6 else 25 if bv>1e5 else 0)*0.15
        w+=0.15
    return (s/w) if w else 0.0

def compute_target_profile_scores(universe, fundamentals, smart_money, accumulation, insider_signals, sector_themes):
    results = {}
    for stock in universe:
        sym, sector, mcap = stock["symbol"], stock["sector"] or "Industrials", stock["market_cap"] or 0
        if mcap<MA_MIN_MARKET_CAP or mcap>MA_MAX_MARKET_CAP: continue
        fund = fundamentals.get(sym, {})
        if not fund: continue
        vs,bs,gs = _sv(fund), _sb(fund), _sg(fund)
        sms = _ssm(sym, smart_money, accumulation, insider_signals)
        themes = sector_themes.get(sym, [])
        mh = sum(1 for t in themes if isinstance(t,str) and any(kw in t.lower() for kw in MA_KW))
        cb = 25.0 if mh>=3 else 18.0 if mh>=2 else 10.0 if mh>=1 else 0.0
        raw = min(100, vs*0.30+bs*0.25+sms*0.25+gs*0.20+cb)
        mm = next((m for lo,hi,m in MCAP_ATTR if lo<=mcap<hi), 0.5)
        sm_ = SECTOR_MA_BASE_RATES.get(sector, 1.0)
        ts = min(100, raw*mm*sm_)
        results[sym] = {"target_score":round(ts,1),"valuation_score":round(vs,1),
            "balance_sheet_score":round(bs,1),"growth_score":round(gs,1),
            "smart_money_score":round(sms,1),"consolidation_bonus":round(cb,1),
            "mcap_multiplier":round(mm,2),"sector_multiplier":round(sm_,2)}
    return results

def _fetch_ma_news(client, symbols):
    today = datetime.now().strftime("%Y-%m-%d")
    lb = (datetime.now()-timedelta(days=MA_RUMOR_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    news, seen = [], set()
    for sym in symbols:
        try: articles = client.company_news(sym, _from=lb, to=today)
        except Exception: continue
        for a in articles:
            url = a.get("url","")
            if url in seen: continue
            seen.add(url)
            text = ((a.get("headline") or "")+" "+(a.get("summary") or "")).lower()
            if any(kw in text for kw in MA_KW_NEWS):
                news.append({"symbol":sym,"headline":a.get("headline",""),"source":a.get("source",""),
                    "url":url,"datetime":a.get("datetime",0),"summary":a.get("summary","")})
        time.sleep(MA_FINNHUB_DELAY)
    return news

def _fetch_web(symbols):
    if not SERPER_API_KEY: return []
    results, seen, kws = [], set(), {"acqui","merger","buyout","takeover","bid","deal","offer"}
    for sym in symbols[:30]:
        try:
            resp = requests.post("https://google.serper.dev/search",
                headers={"X-API-KEY":SERPER_API_KEY,"Content-Type":"application/json"},
                json={"q":f"{sym} acquisition merger buyout 2026","num":5}, timeout=10)
            if resp.status_code!=200: continue
            for item in resp.json().get("organic",[]):
                url = item.get("link","")
                if url in seen: continue
                seen.add(url)
                text = ((item.get("title") or "")+(item.get("snippet") or "")).lower()
                if any(kw in text for kw in kws):
                    results.append({"symbol":sym,"headline":item.get("title",""),"source":"web_search",
                        "url":url,"datetime":0,"summary":item.get("snippet","")})
            time.sleep(0.5)
        except Exception: pass
    return results

def _classify_llm(batch):
    if not batch or not GEMINI_API_KEY: return []
    atxt = "\n".join(f"[{i}] Symbol:{a['symbol']} Headline:{a['headline']} Source:{a['source']} Summary:{a['summary'][:500]}" for i,a in enumerate(batch))
    prompt = (f"You are an M&A analyst. Classify these articles. Be CONSERVATIVE.\n"
        f"Only credible (>=6) if SPECIFIC details: named acquirer, deal terms, board approval.\n"
        f"Generic 'consolidation' = credibility 1-2.\n\nArticles:\n{atxt}\n\n"
        f'JSON array per article: {{"index":i,"is_ma_relevant":bool,"credibility":1-10,'
        f'"deal_stage":"rumor"|"confirmed_interest"|"definitive_agreement"|"completed"|"denied"|"speculation",'
        f'"acquirer_name":"str or null","expected_premium_pct":num_or_null,"target_symbol":"TICKER",'
        f'"price_impact_direction":"up"|"down"|"neutral","rationale":"brief"}}\nReturn ONLY JSON array.')
    try:
        resp = requests.post(f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=60)
        if resp.status_code!=200: return []
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(re.sub(r"```(?:json)?\s*","",text).strip())
    except Exception as e:
        logger.warning(f"Gemini M&A error: {e}"); return []

def _compute_rumor_scores(news, cls_list, existing):
    today = date.today()
    scores, nmap = {}, {i:n for i,n in enumerate(news)}
    for cls in cls_list:
        idx = cls.get("index")
        if idx is None or idx not in nmap or not cls.get("is_ma_relevant"): continue
        art = nmap[idx]; sym = cls.get("target_symbol") or art["symbol"]
        cred = cls.get("credibility",1)
        if cred<3: continue
        raw = (cred/10.0)*100*STAGE_MULT.get(cls.get("deal_stage","speculation"),0.30)
        ex = existing.get(sym,[])
        if ex:
            ds = max(1,(today-datetime.strptime(ex[0]["date"],"%Y-%m-%d").date()).days)
            raw *= 1.1 if ds<=MA_RUMOR_HALF_LIFE_DAYS else 0.5**(ds/MA_RUMOR_HALF_LIFE_DAYS)
        raw = min(100,raw)
        if sym not in scores or raw>scores[sym]["rumor_score"]:
            scores[sym] = {"rumor_score":round(raw,1),"best_headline":art["headline"][:200],
                "deal_stage":cls.get("deal_stage","speculation"),"credibility":cred,
                "acquirer":cls.get("acquirer_name"),"expected_premium":cls.get("expected_premium_pct"),
                "source":art["source"],"url":art["url"]}
    return scores

def _final_scores(tgt_scores, rum_scores):
    today_str = date.today().isoformat()
    results = []
    for sym in set(tgt_scores)|set(rum_scores):
        tp,rp = tgt_scores.get(sym,{}), rum_scores.get(sym,{})
        tgt,rum = tp.get("target_score",0), rp.get("rumor_score",0)
        iw = 1.0-MA_TARGET_WEIGHT_PROFILE-MA_TARGET_WEIGHT_RUMOR
        ib = math.sqrt(tgt*rum)*iw if tgt>40 and rum>30 else 0
        ms = min(100, tgt*MA_TARGET_WEIGHT_PROFILE+rum*MA_TARGET_WEIGHT_RUMOR+ib)
        if ms<MA_MIN_SCORE_STORE: continue
        p = []
        if tgt>50: p.append(f"Strong target profile ({tgt:.0f})")
        elif tgt>30: p.append(f"Moderate target profile ({tgt:.0f})")
        if rum>50:
            acq = rp.get("acquirer")
            p.append(f"Credible M&A {rp.get('deal_stage','rumor')}{f' by {acq}' if acq else ''} ({rum:.0f})")
        elif rum>20: p.append(f"Weak M&A rumor ({rum:.0f})")
        if tgt>40 and rum>30: p.append("Profile+rumor convergence")
        results.append({"symbol":sym,"date":today_str,"ma_score":round(ms,1),
            "target_profile_score":round(tgt,1),"rumor_score":round(rum,1),
            "valuation_score":tp.get("valuation_score"),"balance_sheet_score":tp.get("balance_sheet_score"),
            "growth_score":tp.get("growth_score"),"smart_money_score":tp.get("smart_money_score"),
            "consolidation_bonus":tp.get("consolidation_bonus"),"mcap_multiplier":tp.get("mcap_multiplier"),
            "sector_multiplier":tp.get("sector_multiplier"),"deal_stage":rp.get("deal_stage"),
            "rumor_credibility":rp.get("credibility"),"acquirer_name":rp.get("acquirer"),
            "expected_premium_pct":rp.get("expected_premium"),"best_headline":rp.get("best_headline"),
            "narrative":". ".join(p) if p else f"M&A score: {ms:.0f}","status":"active"})
    return results

_COLS = ("symbol","date","ma_score","target_profile_score","rumor_score","valuation_score",
    "balance_sheet_score","growth_score","smart_money_score","consolidation_bonus","mcap_multiplier",
    "sector_multiplier","deal_stage","rumor_credibility","acquirer_name","expected_premium_pct",
    "best_headline","narrative","status")

def _write(signals, rum_scores):
    today_str = date.today().isoformat()
    if signals:
        with get_conn() as conn:
            conn.execute("DELETE FROM ma_signals WHERE date=?",[today_str])
            conn.executemany(f"INSERT INTO ma_signals ({','.join(_COLS)}) VALUES ({','.join('?'*len(_COLS))})",
                [tuple(s[c] for c in _COLS) for s in signals])
    if rum_scores:
        rows = [(sym,today_str,d.get("source",""),d.get("best_headline",""),d.get("credibility",0),
                 d.get("deal_stage","speculation"),d.get("expected_premium"),d.get("acquirer"),d.get("url",""))
                for sym,d in rum_scores.items()]
        upsert_many("ma_rumors",["symbol","date","rumor_source","rumor_headline",
            "credibility_score","deal_stage","expected_premium_pct","acquirer_name","url"],rows)

def run():
    print("\n"+"="*60+"\n  M&A INTELLIGENCE MODULE\n"+"="*60)
    init_db()
    universe = _load_universe()
    print(f"  {len(universe)} stocks in universe")
    fund, sm, acc, ins = _load_fundamentals(), _load_smart_money(), _load_13f_accum(), _load_insider_signals()
    st_rows = query("SELECT symbol,key_catalysts FROM sector_expert_signals WHERE date>=date('now','-14 days') AND key_catalysts IS NOT NULL")
    sthemes = {}
    for r in st_rows:
        try: cats = json.loads(r["key_catalysts"]) if isinstance(r["key_catalysts"],str) else []
        except (json.JSONDecodeError,TypeError): cats = [r["key_catalysts"]] if r["key_catalysts"] else []
        sthemes.setdefault(r["symbol"],[]).extend(cats)
    try:
        er = query("SELECT symbol,date,rumor_source,rumor_headline,credibility_score,deal_stage,expected_premium_pct FROM ma_rumors WHERE date>=date('now','-30 days') ORDER BY date DESC")
        existing = {}
        for r in er: existing.setdefault(r["symbol"],[]).append(dict(r))
    except Exception: existing = {}
    print("  [1/3] Target profile scores...")
    tgt_scores = compute_target_profile_scores(universe, fund, sm, acc, ins, sthemes)
    print(f"  {len(tgt_scores)} scored, {sum(1 for v in tgt_scores.values() if v['target_score']>30)} above noise")
    print("  [2/3] Scanning M&A rumors...")
    top = sorted(tgt_scores.items(), key=lambda x:x[1]["target_score"], reverse=True)[:50]
    scan = list({s for s,_ in top}|set(existing.keys()))
    rum_scores = {}
    if FINNHUB_API_KEY and GEMINI_API_KEY:
        news = _fetch_ma_news(finnhub.Client(api_key=FINNHUB_API_KEY), scan)
        news.extend(_fetch_web([s for s,_ in top[:20]]))
        print(f"  {len(news)} M&A articles")
        if news:
            all_cls = []
            for i in range(0,len(news),MA_NEWS_BATCH_SIZE):
                all_cls.extend(_classify_llm(news[i:i+MA_NEWS_BATCH_SIZE]))
                if i+MA_NEWS_BATCH_SIZE<len(news): time.sleep(MA_GEMINI_DELAY)
            print(f"  Credible: {sum(1 for c in all_cls if c.get('is_ma_relevant') and c.get('credibility',0)>=3)}")
            rum_scores = _compute_rumor_scores(news, all_cls, existing)
    else: print("  Skipping rumor scan (missing API keys)")
    print("  [3/3] Final M&A scores...")
    signals = _final_scores(tgt_scores, rum_scores)
    _write(signals, rum_scores)
    high = sorted([s for s in signals if s["ma_score"]>=50], key=lambda x:x["ma_score"], reverse=True)
    print(f"  Total: {len(signals)} signals, {len(high)} above 50")
    for sym,d in sorted(rum_scores.items(), key=lambda x:x[1]["rumor_score"], reverse=True)[:5]:
        print(f"    {sym:6s} cred={d['credibility']}/10 stage={d['deal_stage']} score={d['rumor_score']:.0f}")
    for s in high[:10]:
        rt = f"  rumor={s['rumor_score']:.0f}" if s["rumor_score"] and s["rumor_score"]>20 else ""
        print(f"    {s['symbol']:6s} ma={s['ma_score']:.0f} target={s['target_profile_score']:.0f}{rt}")
    print("="*60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
