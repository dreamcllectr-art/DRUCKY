"""13F Filing Tracker — Smart Money Intelligence from SEC EDGAR."""
import sys, json, re, time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import EDGAR_BASE, EDGAR_HEADERS, TRACKED_13F_MANAGERS, CUSIP_MAP_PATH
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

_OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
_US_EXCH = {"US","UN","UA","UF","UW","UT","UP","UV"}  # US exchange codes

def _openfigi_batch(cusips):
    """Resolve up to 100 CUSIPs → tickers via OpenFIGI (free, no key needed)."""
    result = {}
    try:
        payload = [{"idType": "ID_CUSIP", "idValue": c} for c in cusips]
        resp = requests.post(_OPENFIGI_URL, json=payload,
            headers={"Content-Type": "application/json"}, timeout=30)
        resp.raise_for_status()
        for cusip, item in zip(cusips, resp.json()):
            if "data" not in item: continue
            # Prefer US exchange equity
            for entry in item["data"]:
                if (entry.get("exchCode","") in _US_EXCH and
                        entry.get("securityType","") in ("Common Stock","ETP")):
                    result[cusip] = entry["ticker"]; break
            if cusip not in result:
                # Fallback: first equity entry
                for entry in item["data"]:
                    if entry.get("securityType","") in ("Common Stock","ETP"):
                        result[cusip] = entry["ticker"]; break
    except Exception as e: print(f"  OpenFIGI error: {e}")
    return result

def _build_cusip_map():
    return {}  # SEC tickers endpoint has no CUSIP field; map built on-demand via OpenFIGI

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
    xml_url = None
    # Try JSON index first
    try:
        resp = requests.get(f"{base}/{acc}-index.json", headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status(); idx = resp.json()
        for doc in idx.get("documents",[]):
            dt,fn = doc.get("type","").lower(), doc.get("filename","").lower()
            if "information table" in dt or fn.endswith(".xml"):
                xml_url = f"{base}/{doc.get('filename')}"; break
    except Exception:
        pass
    # Fall back to HTML index to find actual XML filename
    if not xml_url:
        try:
            resp = requests.get(f"{base}/{acc}-index.htm", headers=EDGAR_HEADERS, timeout=20)
            resp.raise_for_status()
            # Find all XML links that look like info tables (not primary_doc.xml, not xslForm paths)
            candidates = re.findall(r'href="(/Archives[^"]+\.xml)"', resp.text)
            for c in candidates:
                fn = c.split("/")[-1].lower()
                if "primary_doc" not in fn and "xsl" not in c.lower():
                    xml_url = f"https://www.sec.gov{c}"; break
        except Exception:
            pass
    if not xml_url: xml_url = f"{base}/infotable.xml"
    try:
        resp = requests.get(xml_url, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e: print(f"  XML error {acc}: {e}"); return []
    return _parse_info_table(resp.text)

def _parse_info_table(xml_content):
    positions = []
    try:
        c = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"','',xml_content)
        c = re.sub(r'\s+xsi:\w+="[^"]*"','',c)
        c = re.sub(r'<(/?)\w+:','<\\1',c)
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
    rows = query("""
        SELECT f.cik, f.manager_name, f.symbol, f.shares_held, f.market_value, f.action,
               f.period_of_report, f.rank_in_portfolio, f.portfolio_pct
        FROM filings_13f f
        INNER JOIN (
            SELECT cik, symbol, MAX(period_of_report) AS max_por
            FROM filings_13f WHERE symbol != ''
            GROUP BY cik, symbol
        ) m ON f.cik = m.cik AND f.symbol = m.symbol AND f.period_of_report = m.max_por
    """)
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
        # Batch-resolve unknown CUSIPs via OpenFIGI (100 per request)
        unknown = [p["cusip"] for p in positions if p["cusip"] not in cmap]
        if unknown:
            for i in range(0, len(unknown), 10):
                batch = unknown[i:i+10]
                resolved = _openfigi_batch(batch)
                cmap.update(resolved)
                time.sleep(0.3)  # OpenFIGI free tier: 25 req/min
            _save_cusip_map(cmap)
        tpos = []
        for p in positions:
            tk = cmap.get(p["cusip"])
            if tk and tk not in SKIP_TICKERS: p["symbol"]=tk; tpos.append(p)
        if not tpos: print(f"  No ticker matches (0/{len(positions)} CUSIPs resolved)"); continue
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
    if cmap: _save_cusip_map(cmap)
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
