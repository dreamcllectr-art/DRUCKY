"""13F Filing Tracker — Smart Money Intelligence from SEC EDGAR."""
import sys, json, re, time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import EDGAR_BASE, EDGAR_HEADERS, TRACKED_13F_MANAGERS, CUSIP_MAP_PATH, FMP_API_KEY, FMP_BASE
from tools.db import init_db, upsert_many, query

_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SUBS_URL = f"{EDGAR_BASE}/submissions/CIK{{cik}}.json"
MANAGER_WEIGHTS = {
    "0001536411":1.0,"0001649339":0.90,"0000813672":0.85,"0001336920":0.85,
    "0001167483":0.75,"0001336528":0.75,"0001103804":0.75,
}
SKIP_TICKERS = {"","N/A","CASH","MONY"}

def _load_cusip_map():
    if CUSIP_MAP_PATH.exists():
        try:
            with open(CUSIP_MAP_PATH) as f: return json.load(f)
        except Exception: pass
    return {}

def _save_cusip_map(m):
    CUSIP_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CUSIP_MAP_PATH,"w") as f: json.dump(m, f)

def _build_cusip_map():
    print("  Building CUSIP map from SEC...")
    try:
        resp = requests.get(_TICKERS_URL, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status(); data = resp.json()
        fields = data.get("fields",[])
        ti = fields.index("ticker") if "ticker" in fields else 2
        ci = fields.index("cusip") if "cusip" in fields else -1
        if ci == -1: return {}
        cm = {}
        for row in data.get("data",[]):
            if len(row)>ci and row[ci]:
                c,t = str(row[ci]).strip(), str(row[ti]).strip()
                if c and t: cm[c] = t
        print(f"  CUSIP map: {len(cm):,} entries"); return cm
    except Exception as e: print(f"  CUSIP map failed: {e}"); return {}

def _cusip_fmp(cusip):
    if not FMP_API_KEY: return None
    try:
        resp = requests.get(f"{FMP_BASE}/search",params={"query":cusip,"limit":1,"apikey":FMP_API_KEY},timeout=10)
        data = resp.json()
        if data and isinstance(data,list): return data[0].get("symbol")
    except Exception: pass
    return None

def _latest_13f(cik):
    try:
        resp = requests.get(_SUBS_URL.format(cik=cik), headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status(); data = resp.json()
    except Exception as e: print(f"  Submissions error CIK {cik}: {e}"); return None
    fi = data.get("filings",{}).get("recent",{})
    for i,form in enumerate(fi.get("form",[])):
        if form in ("13F-HR","13F-HR/A"):
            return fi["accessionNumber"][i], fi["filingDate"][i], fi["reportDate"][i]
    return None

def _already_done(cik, acc):
    return len(query("SELECT 1 FROM filings_13f WHERE cik=? AND accession_number=? LIMIT 1",[cik,acc]))>0

def _prior_pos(cik, por):
    rows = query("SELECT symbol,shares_held FROM filings_13f WHERE cik=? AND period_of_report<? ORDER BY period_of_report DESC",[cik,por])
    p = {}
    for r in rows:
        if r["symbol"] not in p: p[r["symbol"]] = r["shares_held"] or 0
    return p

def _action(prior, cur):
    if prior is None: return "NEW" if cur>0 else "UNCHANGED"
    if prior>0 and cur==0: return "EXIT"
    if prior==0: return "NEW" if cur>0 else "UNCHANGED"
    ratio = cur/prior
    return "ADD" if ratio>=1.10 else "CUT" if ratio<=0.50 else "TRIM" if ratio<0.90 else "UNCHANGED"

def _parse_xml(cik, acc):
    ad = acc.replace("-",""); base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{ad}"
    try:
        resp = requests.get(f"{base}/{acc}-index.json", headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status(); idx = resp.json()
    except Exception as e: print(f"  Index error {acc}: {e}"); return []
    xml_url = None
    for doc in idx.get("documents",[]):
        dt,fn = doc.get("type","").lower(), doc.get("filename","").lower()
        if "information table" in dt or fn.endswith(".xml"):
            xml_url = f"{base}/{doc.get('filename')}"; break
    if not xml_url: xml_url = f"{base}/infotable.xml"
    try:
        resp = requests.get(xml_url, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e: print(f"  XML error {acc}: {e}"); return []
    return _parse_info_table(resp.text)

def _parse_info_table(xml_content):
    positions = []
    try:
        c = re.sub(r'\s+xmlns[^"]*"[^"]*"','',xml_content)
        c = re.sub(r'</?ns\d+:','<',c)
        root = ET.fromstring(c)
        def ft(node,*tags):
            for t in tags:
                el = node.find(f".//{t}")
                if el is not None and el.text: return el.text.strip()
            return ""
        for entry in root.iter("infoTable"):
            cusip = ft(entry,"cusip"); vs = ft(entry,"value")
            inv = ft(entry,"investmentDiscretion") or "COM"
            se = entry.find(".//shrsOrPrnAmt"); shares = 0
            if se is not None:
                try: shares = int(ft(se,"sshPrnamt","sshOrPrnAmt").replace(",",""))
                except (ValueError,AttributeError): shares = 0
            pc = ft(entry,"putCall")
            if pc: inv = pc.upper()
            try: val = int(str(vs).replace(",",""))
            except (ValueError,AttributeError): val = 0
            if shares>0 and cusip:
                positions.append({"cusip":cusip.strip(),"issuer":ft(entry,"nameOfIssuer"),
                    "shares_held":shares,"market_value":val,"investment_type":inv or "COM"})
    except ET.ParseError as e: print(f"  XML parse error: {e}")
    return positions

def _smart_money_scores(universe, today):
    rows = query("SELECT cik,manager_name,symbol,shares_held,market_value,action,"
        "period_of_report,rank_in_portfolio,portfolio_pct FROM filings_13f WHERE symbol!='' "
        "GROUP BY cik,symbol HAVING period_of_report=MAX(period_of_report)")
    by_sym = {}
    for r in rows: by_sym.setdefault(r["symbol"],[]).append(r)
    srows = []
    for sym,pos in by_sym.items():
        if sym not in universe: continue
        mc = len(pos); tmv = sum(p["market_value"] or 0 for p in pos)
        nc = sum(p.get("shares_held",0) or 0 for p in pos if p.get("action") in ("NEW","ADD"))
        nc -= sum(p.get("shares_held",0) or 0 for p in pos if p.get("action") in ("EXIT","CUT"))
        np_ = sum(1 for p in pos if p.get("action")=="NEW")
        ex = sum(1 for p in pos if p.get("action")=="EXIT")
        bs = 0.0
        for p in pos:
            w = MANAGER_WEIGHTS.get(p["cik"],0.70)
            bs += 15.0*w
            if p.get("action")=="NEW": bs+=10.0*w
            elif p.get("action")=="ADD": bs+=5.0*w
            elif p.get("action") in ("EXIT","CUT"): bs-=8.0*w
            rk = p.get("rank_in_portfolio") or 999
            if rk<=5: bs+=8.0*w
            elif rk<=10: bs+=4.0*w
        th = json.dumps([{"manager":p["manager_name"],"portfolio_pct":p.get("portfolio_pct")}
            for p in sorted(pos,key=lambda x:x.get("portfolio_pct") or 0,reverse=True)[:5]])
        srows.append((sym,today,mc,tmv,nc,np_,ex,min(100.0,max(0.0,bs)),th))
    if srows:
        upsert_many("smart_money_scores",["symbol","date","manager_count","total_market_value",
            "net_change_shares","new_positions","exits","conviction_score","top_holders"],srows)
        print(f"  Smart money scores: {len(srows)} symbols")

_13F_COLS = ["cik","manager_name","symbol","period_of_report","filing_date","accession_number",
    "cusip","shares_held","market_value","investment_type","prior_shares","change_shares",
    "change_pct","action","rank_in_portfolio","portfolio_pct"]

def run():
    init_db(); today = date.today().isoformat()
    print("13F Filings: Loading smart money positions...")
    cmap = _load_cusip_map()
    if len(cmap)<100:
        cmap = _build_cusip_map()
        if cmap: _save_cusip_map(cmap)
    fmp_cache = {}
    uni = {r["symbol"] for r in query("SELECT symbol FROM stock_universe")}
    nf = 0
    for cik,mgr in TRACKED_13F_MANAGERS.items():
        print(f"\n  [{mgr}]"); time.sleep(0.15)
        info = _latest_13f(cik)
        if not info: print(f"  No 13F for {mgr}"); continue
        acc,fdate,por = info
        print(f"  Latest: {acc} (period:{por} filed:{fdate})")
        if _already_done(cik,acc): print("  Already processed"); continue
        time.sleep(0.15)
        positions = _parse_xml(cik,acc)
        if not positions: print("  No positions"); continue
        print(f"  Parsed {len(positions)} positions")
        tpos = []
        for p in positions:
            cusip = p["cusip"]; tk = cmap.get(cusip)
            if not tk:
                if cusip not in fmp_cache: fmp_cache[cusip]=_cusip_fmp(cusip); time.sleep(0.1)
                tk = fmp_cache.get(cusip)
            if tk and tk not in SKIP_TICKERS: p["symbol"]=tk; tpos.append(p)
        tv = sum(p["market_value"] for p in tpos if p["market_value"]) or 1
        tpos.sort(key=lambda x:x.get("market_value") or 0, reverse=True)
        prior = _prior_pos(cik, por)
        rows = []
        for rank,p in enumerate(tpos,1):
            sym,ps,cs = p["symbol"], prior.get(p["symbol"]), p["shares_held"]
            act = _action(ps,cs); chg = cs-(ps or 0)
            cpct = (chg/ps*100) if ps and ps>0 else None
            ppct = (p["market_value"]/tv*100) if p["market_value"] else None
            rows.append((cik,mgr,sym,por,fdate,acc,p["cusip"],cs,p["market_value"],
                p["investment_type"],ps,chg,cpct,act,rank,ppct))
        if rows:
            upsert_many("filings_13f",_13F_COLS,rows)
            print(f"  Stored {len(rows)} | NEW:{sum(1 for r in rows if r[13]=='NEW')} EXIT:{sum(1 for r in rows if r[13]=='EXIT')}")
            nf += 1
        for cusip,tk in fmp_cache.items():
            if tk: cmap[cusip]=tk
        _save_cusip_map(cmap)
    print(f"\n  Recomputing smart money scores...")
    _smart_money_scores(uni, today)
    top = query("SELECT s.symbol,s.conviction_score,s.manager_count FROM smart_money_scores s "
        "WHERE s.date=(SELECT MAX(date) FROM smart_money_scores WHERE symbol=s.symbol) "
        "ORDER BY s.conviction_score DESC LIMIT 15")
    if top:
        print(f"\n  TOP SMART MONEY:  {'Sym':<8}{'Score':>6}{'Mgrs':>6}")
        for r in top: print(f"  {r['symbol']:<8}{r['conviction_score']:>6.1f}{r['manager_count']:>6}")
    print(f"\n13F complete: {nf} new filings processed")

if __name__ == "__main__": run()
