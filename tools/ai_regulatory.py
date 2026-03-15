"""AI Regulatory Intelligence -- global AI regulation stock impact signals."""
import sys, json, time, logging, re
from datetime import date, datetime, timedelta
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import (GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL, SERPER_API_KEY, EDGAR_HEADERS,
    AI_REG_FETCH_LIMIT, AI_REG_CLASSIFICATION_BATCH_SIZE, AI_REG_GEMINI_DELAY, AI_REG_LOOKBACK_DAYS,
    AI_REG_SEVERITY_WEIGHTS, AI_REG_SECTOR_EXPOSURE, AI_REG_JURISDICTION_WEIGHTS)
from tools.db import init_db, upsert_many, query
logger = logging.getLogger(__name__)
FR_BASE = "https://www.federalregister.gov/api/v1"
SEC_BASE = "https://efts.sec.gov/LATEST"
_NAMES = {"federal_register":"Federal Register (US)","sec":"SEC","ftc":"FTC","state_us":"US State Legislatures",
    "sector_banking":"Banking Regulators","sector_healthcare":"Healthcare Regulators","sector_employment":"Employment Regulators",
    "eu_commission":"EU Commission / AI Act","eu_dsa_dma":"EU DSA/DMA","uk_aisi":"UK AI Safety Institute",
    "uk_fca_ico":"UK FCA / ICO","china_cac":"China CAC / MIIT","japan_meti":"Japan METI",
    "korea_pipc":"South Korea PIPC","singapore_imda":"Singapore IMDA","canada_aida":"Canada AIDA",
    "global_coordination":"G7/OECD/UN"}
def _im(hs,ts,hsym,tsym): return {"headwind_sectors":hs,"tailwind_sectors":ts,"headwind_symbols":hsym,"tailwind_symbols":tsym}
_T,_CS,_F,_I,_HC = "Technology","Communication Services","Financials","Industrials","Health Care"
IMPACT_MAP = {
    "ai_model_regulation":_im([_T,_CS],[],["GOOGL","META","MSFT","AMZN","NVDA","CRM","PLTR","AI","SAP","BABA"],[]),
    "ai_transparency_disclosure":_im([_T,_CS,_F],[],["GOOGL","META","MSFT","CRM","NOW","PLTR","SAP"],["MSFT","IBM","SAP"]),
    "ai_copyright_ip":_im([_T,_CS],[],["GOOGL","META","MSFT","ADBE","AI"],["DIS","NFLX","WBD","SPOT"]),
    "ai_liability_safety":_im([_T,_I],["Insurance"],["TSLA","GOOGL","MSFT","AMZN"],[]),
    "ai_employment_hr":_im([_T],[],["WDAY","NOW","CRM","HIMS"],[]),
    "ai_healthcare":_im([_HC],[],["ISRG","VEEV","DXCM","TDOC"],[]),
    "ai_financial_services":_im([_F],[],["GS","JPM","MS","SCHW","HOOD","UPST","SOFI"],[]),
    "ai_autonomous_vehicles":_im(["Consumer Discretionary",_I],[],["TSLA","GM","F","UBER","LYFT"],[]),
    "ai_data_privacy":_im([_T,_CS],[],["META","GOOGL","AMZN","CRM","PLTR"],["CRWD","ZS","PANW"]),
    "ai_export_controls":_im([_T],[],["NVDA","AMD","INTC","AVGO","ASML","AMAT","LRCX","TSM"],[]),
    "ai_antitrust":_im([_T],[],["GOOGL","META","MSFT","AMZN","AAPL","NVDA"],["AMD","INTC"]),
    "ai_government_adoption":_im([],[_T,_I],[],["PLTR","AI","GOOG","MSFT","AMZN","IBM","SAP","ACN"]),
    "ai_infrastructure_investment":_im([],[_T,_I],[],["NVDA","AMD","INTC","AVGO","AMAT","MSFT","GOOGL","AMZN","ASML","TSM","ARM"]),
    "ai_cross_border_data":_im([_T,_CS,_F],[],["GOOGL","META","AMZN","MSFT","CRM","SNOW","DDOG","PLTR"],["SAP","IBM"]),
    "ai_international_standards":_im([],[_T],[],["MSFT","IBM","SAP","ACN","GOOGL"]),
    "ai_sovereign_compute":_im([],[_T,_I],["AMZN","MSFT","GOOGL"],["NVDA","AMD","INTC","ASML","TSM","ARM","AMAT"]),
}

def _dedup(events): seen = set(); return [e for e in events if e["doc_id"] not in seen and not seen.add(e["doc_id"])]

def _fetch_federal_register():
    events = []; cutoff = (date.today()-timedelta(days=AI_REG_LOOKBACK_DAYS)).isoformat()
    for term in ["artificial intelligence","machine learning","automated decision","algorithmic"]:
        try:
            resp = requests.get(f"{FR_BASE}/documents.json", params={"conditions[term]":term,
                "conditions[publication_date][gte]":cutoff,"conditions[type][]":["RULE","PRORULE","NOTICE"],
                "per_page":20,"order":"newest","fields[]":["title","abstract","publication_date","type","agencies","document_number","html_url"]}, timeout=15)
            resp.raise_for_status()
            for d in resp.json().get("results",[]):
                events.append({"source":"federal_register","title":d.get("title",""),"abstract":(d.get("abstract") or "")[:500],
                    "date":d.get("publication_date",""),"doc_type":d.get("type",""),
                    "agencies":", ".join(a.get("name","") for a in (d.get("agencies") or [])),
                    "url":d.get("html_url",""),"doc_id":d.get("document_number",""),"jurisdiction":"US"})
            time.sleep(0.5)
        except Exception as e: logger.warning(f"FR '{term}' failed: {e}")
    return _dedup(events)[:AI_REG_FETCH_LIMIT]

def _fetch_sec():
    events = []; cutoff = (date.today()-timedelta(days=AI_REG_LOOKBACK_DAYS)).isoformat()
    for term in ["artificial intelligence","AI risk","algorithmic trading"]:
        try:
            resp = requests.get(f"{SEC_BASE}/search-index", params={"q":f'"{term}"',"dateRange":"custom",
                "startdt":cutoff,"enddt":date.today().isoformat(),"forms":"RULE,NOTICE,PRESS,LITIGATION"}, headers=EDGAR_HEADERS, timeout=15)
            resp.raise_for_status()
            for h in resp.json().get("hits",{}).get("hits",[])[:10]:
                s = h.get("_source",{})
                events.append({"source":"sec","title":s.get("display_name_t",s.get("file_description","")),
                    "abstract":(s.get("file_description","") or "")[:500],"date":(s.get("file_date","") or "")[:10],
                    "doc_type":s.get("form_type",""),"agencies":"SEC",
                    "url":f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={s.get('file_num','')}",
                    "doc_id":s.get("_id",h.get("_id","")),"jurisdiction":"US"})
            time.sleep(0.5)
        except Exception as e: logger.warning(f"SEC '{term}' failed: {e}")
    return [e for e in _dedup(events) if e.get("doc_id")][:AI_REG_FETCH_LIMIT]

def _date_from_snippet(sn):
    for pat in [r"(\d{4}-\d{2}-\d{2})",r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})"]:
        m = re.search(pat, sn)
        if m:
            raw = m.group(1)
            if "-" in raw: return raw
            for f in ("%B %d, %Y","%B %d %Y","%b %d, %Y","%b %d %Y"):
                try: return datetime.strptime(raw,f).strftime("%Y-%m-%d")
                except ValueError: pass
    return date.today().isoformat()

def _serper_fetch(queries, endpoint="news"):
    if not SERPER_API_KEY: return []
    events = []
    for src,q,jur,dt,num in queries:
        try:
            resp = requests.post(f"https://google.serper.dev/{endpoint}",
                headers={"X-API-KEY":SERPER_API_KEY,"Content-Type":"application/json"},json={"q":q,"num":num},timeout=15)
            resp.raise_for_status()
            for r in resp.json().get("news" if endpoint=="news" else "organic",[]):
                events.append({"source":src,"title":r.get("title",""),"abstract":(r.get("snippet","") or "")[:500],
                    "date":(r.get("date","") or "")[:10] or _date_from_snippet(r.get("snippet","")),
                    "doc_type":dt,"agencies":_NAMES.get(src,src),"url":r.get("link",""),"doc_id":r.get("link",""),"jurisdiction":jur})
            time.sleep(0.5)
        except Exception as e: logger.warning(f"Serper ({src}) failed: {e}")
    return _dedup(events)[:AI_REG_FETCH_LIMIT]

def _sq(s,q,j,d,n): return (s,q,j,d,n)
_SQ = {"ftc":[_sq("ftc","site:ftc.gov artificial intelligence AI enforcement 2025 2026","US","enforcement",15)],
    "eu":[_sq("eu_commission","EU AI Act implementation enforcement 2025 2026","EU","news",10),_sq("eu_commission","European Commission AI regulation compliance","EU","news",10)],
    "state":[_sq("state_us","(California OR Colorado OR Texas OR New York) AI law regulation 2025 2026","US","legislation",15)],
    "sector":[_sq("sector_banking","OCC Fed FDIC AI banking regulation 2025 2026","US","sector_regulation",8),
        _sq("sector_healthcare","FDA HHS AI healthcare regulation 2025 2026","US","sector_regulation",8),
        _sq("sector_employment","EEOC DOL AI hiring discrimination 2025 2026","US","sector_regulation",8)],
    "uk":[_sq("uk_aisi","UK AI Safety Institute regulation 2025 2026","UK","regulation",8),
        _sq("uk_fca_ico","UK FCA ICO AI financial data enforcement 2025 2026","UK","regulation",8)],
    "china":[_sq("china_cac","China CAC generative AI regulation 2025 2026","CN","regulation",8),
        _sq("china_cac","China AI chip export restriction semiconductor 2025 2026","CN","regulation",8)],
    "apac":[_sq("japan_meti","Japan AI regulation METI 2025 2026","JP","regulation",6),
        _sq("korea_pipc","South Korea AI Basic Act PIPC 2025 2026","KR","regulation",6),
        _sq("singapore_imda","Singapore AI Verify IMDA governance 2025 2026","SG","regulation",6)],
    "canada":[_sq("canada_aida","Canada AIDA Artificial Intelligence Data Act 2025 2026","CA","legislation",8)],
    "global":[_sq("global_coordination","G7 OECD UN AI governance 2025 2026","GLOBAL","multilateral",6)],
    "dsa":[_sq("eu_dsa_dma","EU Digital Services Markets Act AI enforcement 2025 2026","EU","enforcement",8)]}

def _classify(events):
    if not GEMINI_API_KEY: return []
    cats = list(IMPACT_MAP.keys()); classified = []
    for i in range(0,len(events),AI_REG_CLASSIFICATION_BATCH_SIZE):
        batch = events[i:i+AI_REG_CLASSIFICATION_BATCH_SIZE]
        texts = [f"{j+1}. [{e['source'].upper()}] [{e.get('jurisdiction','US')}] \"{e['title']}\" | {e['date']} | {e['agencies']} | {e['abstract'][:200]}" for j,e in enumerate(batch)]
        prompt = (f"Classify AI regulatory events for US stock impact. Categories: {json.dumps(cats)}\n"
            "Severity:1-5 Stage:proposed|final_rule|enforcement|enacted|guidance Direction:headwind|tailwind|mixed Timeline:immediate|6_months|1_year|2_plus_years\n"
            f"Events:\n{chr(10).join(texts)}\nReturn JSON array: [{{\"index\":N,\"is_significant\":bool,\"impact_category\":\"...\",\"severity\":1-5,\"stage\":\"...\",\"direction\":\"...\",\"timeline\":\"...\",\"specific_symbols\":[],\"jurisdiction\":\"...\",\"rationale\":\"...\"}}]")
        try:
            resp = requests.post(f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
                headers={"Content-Type":"application/json"},params={"key":GEMINI_API_KEY},
                json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.2,"maxOutputTokens":2048}},timeout=30)
            resp.raise_for_status(); text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text.startswith("```"): text = text.split("\n",1)[1].rsplit("```",1)[0].strip()
            for c in json.loads(text):
                idx = c.get("index",0)-1
                if 0<=idx<len(batch) and c.get("is_significant"):
                    ev = batch[idx].copy()
                    ev.update({k:c.get(k,d) for k,d in [("impact_category",None),("severity",1),("stage","guidance"),
                        ("direction","mixed"),("timeline","1_year"),("specific_symbols",[]),("rationale","")]})
                    ev["jurisdiction"] = c.get("jurisdiction") or ev.get("jurisdiction","US"); classified.append(ev)
        except Exception as e: logger.warning(f"Gemini batch error: {e}")
        time.sleep(AI_REG_GEMINI_DELAY)
    return classified

def _score_symbols(classified):
    stocks = query("SELECT symbol,sector FROM stock_universe WHERE symbol IS NOT NULL AND sector IS NOT NULL")
    smap = {r["symbol"]:r["sector"] for r in stocks}
    sw = {"guidance":0.3,"proposed":0.5,"final_rule":0.8,"enforcement":0.9,"enacted":1.0}
    tw = {"immediate":1.0,"6_months":0.8,"1_year":0.5,"2_plus_years":0.3}
    ss: dict[str,list] = {}
    for ev in classified:
        cat = ev.get("impact_category")
        if not cat or cat not in IMPACT_MAP: continue
        imp = IMPACT_MAP[cat]; d = ev.get("direction","mixed")
        ew = AI_REG_SEVERITY_WEIGHTS.get(ev.get("severity",1),0.2)*sw.get(ev.get("stage","guidance"),0.3)*tw.get(ev.get("timeline","1_year"),0.5)*AI_REG_JURISDICTION_WEIGHTS.get(ev.get("jurisdiction","US"),0.3)
        info = {"title":ev.get("title","")[:100],"category":cat,"severity":ev.get("severity",1),"stage":ev.get("stage",""),"direction":d,"source":ev.get("source",""),"weight":round(ew,3)}
        for sym,sec in smap.items():
            impact = 0.0; se = AI_REG_SECTOR_EXPOSURE.get(sec,0.1)
            if sec in imp.get("headwind_sectors",[]): impact = -ew*se*0.6
            elif sec in imp.get("tailwind_sectors",[]): impact = ew*se*0.6
            if sym in imp.get("headwind_symbols",[]): impact -= ew*0.9
            if sym in imp.get("tailwind_symbols",[]): impact += ew*0.9
            if sym in ev.get("specific_symbols",[]):
                impact += ew*(-0.8 if d=="headwind" else 0.8 if d=="tailwind" else -0.4)
            if d=="tailwind": impact = abs(impact)
            elif d=="mixed": impact *= 0.5
            if abs(impact)>0.005: ss.setdefault(sym,[]).append({**info,"impact":impact})
    results = {}
    for sym,sigs in ss.items():
        net = sum(s["impact"] for s in sigs); ec = len(set(s["title"] for s in sigs))
        score = max(0.0,min(100.0,(net/1.5+1.0)/2.0*100.0*min(1.5,1.0+(ec-1)*0.1)))
        if abs(score-50.0)>3.0:
            results[sym] = {"score":round(score,2),"events":sorted(sigs,key=lambda s:abs(s["impact"]),reverse=True)[:5],"event_count":ec,"net_impact":round(net,4)}
    return results

def run():
    init_db(); today = date.today().isoformat()
    print("\n" + "="*60 + "\n  AI REGULATORY INTELLIGENCE (GLOBAL)\n" + "="*60)
    all_ev = []
    for lab,fn in [("Federal Register",_fetch_federal_register),("SEC EDGAR",_fetch_sec)]:
        e = fn(); all_ev.extend(e); print(f"  {lab}: {len(e)}")
    for key,(lab,ep) in {"ftc":("FTC","search"),"eu":("EU","news"),"state":("State","news"),"sector":("Sector","news"),
        "uk":("UK","news"),"china":("China","news"),"apac":("APAC","news"),"canada":("Canada","news"),
        "global":("G7/OECD/UN","news"),"dsa":("EU DSA/DMA","news")}.items():
        e = _serper_fetch(_SQ[key],endpoint=ep); all_ev.extend(e); print(f"  {lab}: {len(e)}")
    print(f"\n  Total: {len(all_ev)} events")
    if not all_ev: return
    classified = _classify(all_ev)
    if not classified: print("  No significant events"); return
    scores = _score_symbols(classified)
    if not scores: print("  No scores"); return
    sr = [(s,today,round(d["score"],2),d["event_count"],round(d["net_impact"],4),"active",
        "; ".join(f"[{e['source'].upper()}] {e['title'][:60]}" for e in d["events"][:3])[:500]) for s,d in scores.items()]
    if sr: upsert_many("regulatory_signals",["symbol","date","reg_score","event_count","net_impact","status","narrative"],sr)
    er = [(e.get("doc_id",e.get("url",""))[:128],today,e.get("source",""),e.get("title","")[:300],
        e.get("abstract","")[:500],e.get("date",today),e.get("doc_type",""),e.get("agencies",""),
        e.get("impact_category",""),e.get("severity",1),e.get("stage","guidance"),e.get("direction","mixed"),
        e.get("timeline","1_year"),json.dumps(e.get("specific_symbols",[])),e.get("rationale","")[:300],
        e.get("url",""),e.get("jurisdiction","US")) for e in classified]
    if er: upsert_many("regulatory_events",["event_id","date","source","title","abstract","event_date","doc_type",
        "agencies","impact_category","severity","stage","direction","timeline","specific_symbols","rationale","url","jurisdiction"],er)
    hw = sum(1 for d in scores.values() if d["score"]<45); tw = sum(1 for d in scores.values() if d["score"]>55)
    print(f"\n  {len(scores)} symbols | Headwind:{hw} Neutral:{len(scores)-hw-tw} Tailwind:{tw}")
    for lab,items in [("HEADWINDS",sorted([(s,d) for s,d in scores.items() if d["score"]<45],key=lambda x:x[1]["score"])[:5]),
                      ("TAILWINDS",sorted([(s,d) for s,d in scores.items() if d["score"]>55],key=lambda x:x[1]["score"],reverse=True)[:5])]:
        if items:
            print(f"  {lab}:")
            for s,d in items: print(f"    {s:<8} {d['score']:>6.1f} {d['net_impact']:>+.3f}")
    print(f"  Done: {len(sr)} signals, {len(er)} events\n" + "="*60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
