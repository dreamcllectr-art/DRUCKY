"""Energy Infrastructure Intelligence — interconnection queues, tech cost curves, regulatory signals."""
import sys, os, json, time, argparse, csv, io, re
from datetime import date, datetime
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL
from tools.db import init_db, query, get_conn

CONGRESS_API_KEY = os.getenv("CONGRESS_API_KEY", "")
CONGRESS_API_BASE = "https://api.congress.gov/v3"
CURRENT_CONGRESS = 119
NREL_ATB_URL = "https://oedi-data-lake.s3.amazonaws.com/ATB/electricity/csv/2024/v3.0.0/ATBe.csv"
NREL_TECH_MAP = {"utilitypv":"Utility Solar","landbasedwind":"Onshore Wind","offshorewind":"Offshore Wind",
    "utility-scalepv-plus-battery":"Solar + Storage","nuclear":"Nuclear","naturalgas":"Natural Gas",
    "csp":"Concentrated Solar","geothermal":"Geothermal","hydropower":"Hydro","biopower":"Biomass"}
FUEL_NORMALIZE = {"solar":"Solar","solar photovoltaic":"Solar","photovoltaic":"Solar","wind":"Wind",
    "onshore wind":"Wind","offshore wind":"Offshore Wind","battery":"Battery Storage",
    "battery storage":"Battery Storage","energy storage":"Battery Storage","natural gas":"Natural Gas",
    "gas":"Natural Gas","ng":"Natural Gas","nuclear":"Nuclear","nuclear fission":"Nuclear",
    "hybrid":"Hybrid","solar + storage":"Hybrid","coal":"Coal","pumped":"Hydro","hydro":"Hydro",
    "hydroelectric":"Hydro","geothermal":"Geothermal","biomass":"Biomass"}
QUEUE_TICKERS = {"Solar":["FSLR","ENPH","SEDG","RUN","NOVA","ARRY"],"Wind":["GE","SHLS","TPI"],
    "Battery Storage":["FLUENCE","STEM","ENVX","QS"],"Nuclear":["CEG","VST","NRG","SMR","OKLO","NNE"],
    "Natural Gas":["EQT","RRC","AR","SWN","CTRA"],"Hybrid":["NEE","AES","BEP"],
    "Utilities (Interconnection)":["NEE","DUK","SO","AEP","D","EXC","SRE","WEC","ES","ED"]}
_SCHEMA_SQL = "CREATE TABLE IF NOT EXISTS interconnection_queue (iso TEXT NOT NULL,project_name TEXT,developer TEXT,capacity_mw REAL,fuel_type TEXT,fuel_normalized TEXT,status TEXT,state TEXT,county TEXT,queue_date TEXT,expected_cod TEXT,interconnection_point TEXT,fetched_date TEXT DEFAULT (date('now')),UNIQUE(iso,project_name,capacity_mw));CREATE INDEX IF NOT EXISTS idx_iq_iso_fuel ON interconnection_queue(iso,fuel_normalized);CREATE INDEX IF NOT EXISTS idx_iq_status ON interconnection_queue(status);CREATE TABLE IF NOT EXISTS interconnection_queue_summary (date TEXT NOT NULL,iso TEXT NOT NULL,fuel_type TEXT NOT NULL,active_count INTEGER,active_mw REAL,withdrawn_pct REAL,avg_queue_days REAL,median_cod_year INTEGER,PRIMARY KEY(date,iso,fuel_type));CREATE TABLE IF NOT EXISTS nrel_cost_curves (technology TEXT NOT NULL,scenario TEXT NOT NULL,year INTEGER NOT NULL,metric TEXT NOT NULL,value REAL,unit TEXT,fetched_date TEXT DEFAULT (date('now')),PRIMARY KEY(technology,scenario,year,metric));CREATE TABLE IF NOT EXISTS energy_legislation (bill_id TEXT PRIMARY KEY,congress INTEGER,bill_type TEXT,bill_number INTEGER,title TEXT,introduced_date TEXT,latest_action TEXT,latest_action_date TEXT,sponsor TEXT,cosponsor_count INTEGER,subjects TEXT,status TEXT,energy_relevance_score REAL,affected_sectors TEXT,affected_tickers TEXT,summary TEXT,fetched_date TEXT DEFAULT (date('now')));CREATE INDEX IF NOT EXISTS idx_eleg_congress ON energy_legislation(congress,latest_action_date DESC);CREATE TABLE IF NOT EXISTS energy_regulatory_signals (date TEXT NOT NULL,source TEXT NOT NULL,signal_type TEXT NOT NULL,headline TEXT,detail TEXT,affected_sectors TEXT,affected_tickers TEXT,impact_score REAL,PRIMARY KEY(date,source,headline));"
_IQ = "INSERT OR REPLACE INTO interconnection_queue (iso,project_name,developer,capacity_mw,fuel_type,fuel_normalized,status,state,county,queue_date,expected_cod,interconnection_point,fetched_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"

def _ensure_tables(): c = get_conn(); c.executescript(_SCHEMA_SQL); c.commit()
def _nf(raw):
    if not raw: return "Unknown"
    for k,v in FUEL_NORMALIZE.items():
        if k in str(raw).strip().lower(): return v
    return str(raw).strip().title()
def _ds(v):
    if hasattr(v,"strftime"): return v.strftime("%Y-%m-%d")
    return (str(v).strip()[:10] if v and str(v).strip()[:10] != "None" else None) if v else None
def _fresh(sql, params=(), days=7):
    r = query(sql, params) if params else query(sql)
    if r and r[0]["d"]:
        age = (date.today()-date.fromisoformat(r[0]["d"])).days
        if age < days: print(f"    Data {age}d old, using cache."); return True
    return False
def _gcol(row, cols, names, as_float=False):
    for n in names:
        if n in cols:
            v = row.get(cols[n])
            if v is not None and str(v) not in ("nan",""):
                if as_float:
                    try: return float(v)
                    except (ValueError,TypeError): continue
                return str(v)
    return None

def _fetch_caiso_queue(conn, today):
    try: import openpyxl
    except ImportError: return {"projects":0,"mw":0}
    try:
        resp = requests.get("https://www.caiso.com/documents/publicqueuereport.xlsx", timeout=60); resp.raise_for_status()
        wb = openpyxl.load_workbook(io.BytesIO(resp.content), read_only=True, data_only=True); ws = wb.active; hr = 1
        for ri,row in enumerate(ws.iter_rows(min_row=1,max_row=5,values_only=True),1):
            if "project name" in [str(c or "").strip().lower() for c in row]: hr = ri; break
        hdrs = [str(c.value or "").strip().lower().replace("\n"," ") for c in next(ws.iter_rows(min_row=hr,max_row=hr))]
        rows = []
        for row in ws.iter_rows(min_row=hr+1, values_only=True):
            if not row or not any(row): continue
            rd = dict(zip(hdrs, row)); cap = None
            for c in ["net mws to grid","mw-1","net mw","capacity (mw)","mw"]:
                if c in rd and rd[c]:
                    try: cap = float(rd[c])
                    except: pass
                    if cap is not None: break
            fuel = rd.get("fuel-1",rd.get("fuel type",rd.get("resource type",rd.get("fuel",""))))
            st = rd.get("application status",rd.get("status",rd.get("queue status","")))
            rows.append(("CAISO",str(rd.get("project name",rd.get("name","")))[:200],None,cap,
                str(fuel or ""),_nf(str(fuel or "")),str(st or ""),str(rd.get("state",rd.get("county","CA")))[:50],
                str(rd.get("county",""))[:50] or None,_ds(rd.get("queue date","")),
                _ds(rd.get("current on-line date",rd.get("proposed on-line date (as filed with ir)",""))),
                str(rd.get("station or transmission line",""))[:200] or None,today))
        wb.close()
        if rows: conn.executemany(_IQ, rows); conn.commit()
        act = [r for r in rows if "withdraw" not in (r[6] or "").lower()]
        mw = sum(r[3] or 0 for r in act); print(f"      CAISO: {len(act)} active, {mw:,.0f} MW")
        return {"projects":len(act),"mw":mw}
    except Exception as e: print(f"      CAISO FAILED: {e}"); return {"projects":0,"mw":0}

def _fetch_gridstatus_queues(conn, today):
    try: import gridstatus
    except ImportError: return {}
    imap = {"PJM":gridstatus.PJM,"MISO":gridstatus.MISO,"ERCOT":gridstatus.Ercot,
            "SPP":gridstatus.SPP,"NYISO":gridstatus.NYISO,"ISONE":gridstatus.ISONE}
    res = {}
    for nm,cls in imap.items():
        try:
            df = cls().get_interconnection_queue()
            if df is None or df.empty: res[nm] = {"projects":0,"mw":0}; continue
            cols = {c.lower().replace(" ","_"):c for c in df.columns}; rows = []
            for _,row in df.iterrows():
                cap = _gcol(row,cols,["capacity_mw","capacity_(mw)","mw","summer_capacity_mw","nameplate_capacity_mw"],True)
                fuel = _gcol(row,cols,["fuel_type","generation_type","type","fuel","technology","resource_type"])
                name = (_gcol(row,cols,["project_name","name","facility_name"]) or "")[:200] or None
                state = (_gcol(row,cols,["state","county_state","location"]) or "")[:50] or None
                rows.append((nm,name,None,cap,fuel,_nf(fuel),_gcol(row,cols,["status","queue_status"]),state,None,None,None,None,today))
            conn.executemany(_IQ, rows); conn.commit()
            act = [r for r in rows if r[6] and "withdraw" not in (r[6] or "").lower()]
            mw = sum(r[3] or 0 for r in act); res[nm] = {"projects":len(act),"mw":mw}
            print(f"      {nm}: {len(act)} active, {mw:,.0f} MW")
        except Exception as e: print(f"      {nm} FAILED: {e}"); res[nm] = {"projects":0,"mw":0}
    return res

def fetch_interconnection_queues():
    _ensure_tables(); conn = get_conn(); today = date.today().isoformat()
    if _fresh("SELECT MAX(fetched_date) as d FROM interconnection_queue"): return _summarize_queue()
    conn.execute("DELETE FROM interconnection_queue"); conn.commit()
    tp = tm = 0; c = _fetch_caiso_queue(conn, today); tp += c.get("projects",0); tm += c.get("mw",0)
    for s in (_fetch_gridstatus_queues(conn, today) or {}).values(): tp += s.get("projects",0); tm += s.get("mw",0)
    print(f"\n    TOTAL: {tp} projects, {tm:,.0f} MW")
    sm = _summarize_queue(); _persist_summaries(); return sm

def _summarize_queue():
    W = "status NOT LIKE '%withdraw%' AND status NOT LIKE '%completed%'"; _q = lambda s: query(s) or []
    iso = _q(f"SELECT iso,COUNT(*) as cnt,SUM(capacity_mw) as total_mw FROM interconnection_queue WHERE {W} GROUP BY iso ORDER BY total_mw DESC")
    return {"date":date.today().isoformat(),"iso_summary":iso,
        "fuel_summary":_q(f"SELECT fuel_normalized as fuel,COUNT(*) as cnt,SUM(capacity_mw) as total_mw FROM interconnection_queue WHERE {W} GROUP BY fuel_normalized ORDER BY total_mw DESC"),
        "cod_distribution":_q(f"SELECT SUBSTR(expected_cod,1,4) as cod_year,fuel_normalized as fuel,COUNT(*) as cnt,SUM(capacity_mw) as total_mw FROM interconnection_queue WHERE expected_cod IS NOT NULL AND {W} AND SUBSTR(expected_cod,1,4) BETWEEN '2025' AND '2035' GROUP BY cod_year,fuel_normalized ORDER BY cod_year,total_mw DESC"),
        "nuclear_pipeline":_q(f"SELECT iso,project_name,capacity_mw,status,expected_cod,state FROM interconnection_queue WHERE fuel_normalized='Nuclear' AND {W} ORDER BY capacity_mw DESC LIMIT 30"),
        "battery_by_iso":_q(f"SELECT iso,SUM(capacity_mw) as total_mw,COUNT(*) as cnt FROM interconnection_queue WHERE fuel_normalized='Battery Storage' AND {W} GROUP BY iso ORDER BY total_mw DESC"),
        "total_projects":sum(r["cnt"] for r in iso),"total_mw":sum(r["total_mw"] or 0 for r in iso)}

def _persist_summaries():
    conn = get_conn(); today = date.today().isoformat(); W = "status NOT LIKE '%withdraw%'"
    dr = query(f"SELECT iso,fuel_normalized as fuel,SUM(CASE WHEN {W} THEN 1 ELSE 0 END) as ac,SUM(CASE WHEN {W} THEN capacity_mw ELSE 0 END) as am,ROUND(100.0*SUM(CASE WHEN status LIKE '%withdraw%' THEN 1 ELSE 0 END)/COUNT(*),1) as wp,ROUND(AVG(CASE WHEN queue_date IS NOT NULL AND {W} THEN julianday('now')-julianday(queue_date) END),0) as aqd,CAST(AVG(CASE WHEN expected_cod IS NOT NULL AND {W} THEN CAST(SUBSTR(expected_cod,1,4) AS INTEGER) END) AS INTEGER) as mcy FROM interconnection_queue GROUP BY iso,fuel_normalized HAVING ac>0")
    rows = [(today,r["iso"],r["fuel"],r["ac"],r["am"] or 0,r["wp"] or 0,r["aqd"] or 0,r["mcy"] or 0) for r in (dr or [])]
    if rows: conn.executemany("INSERT OR REPLACE INTO interconnection_queue_summary (date,iso,fuel_type,active_count,active_mw,withdrawn_pct,avg_queue_days,median_cod_year) VALUES (?,?,?,?,?,?,?,?)", rows); conn.commit()

def fetch_nrel_cost_curves():
    _ensure_tables(); conn = get_conn()
    if _fresh("SELECT MAX(fetched_date) as d FROM nrel_cost_curves", days=90): return _nrel_summary()
    try: resp = requests.get(NREL_ATB_URL, timeout=120); resp.raise_for_status()
    except:
        try: resp = requests.get("https://oedi-data-lake.s3.amazonaws.com/ATB/electricity/csv/2024/v2.0.0/ATBe.csv", timeout=120); resp.raise_for_status()
        except: return _nrel_summary()
    rows, today, seen = [], date.today().isoformat(), set()
    for row in csv.DictReader(io.StringIO(resp.text)):
        tl = (row.get("technology",row.get("technology_alias","")) or "").lower().replace("-","").replace(" ","")
        td = next((d for k,d in NREL_TECH_MAP.items() if k in tl), None)
        if not td: continue
        sl = (row.get("scenario","") or "").lower()
        if not any(x in sl for x in ["moderate","mid","advanced","conservative"]): continue
        sn = "Advanced" if any(x in sl for x in ["advanced","low"]) else "Conservative" if any(x in sl for x in ["conservative","high"]) else "Moderate"
        mu = (row.get("core_metric_parameter",row.get("metric","")) or "").upper()
        if not any(m in mu for m in ["LCOE","CAPEX","O&M","CF","OCC","CFC"]): continue
        mn = "LCOE" if "LCOE" in mu else "CAPEX" if "OCC" in mu or "CAPEX" in mu else "CFC" if "CFC" in mu else "Fixed O&M" if "FIXED" in mu else "Variable O&M" if "VARIABLE" in mu else "CF" if "CF" in mu else mu
        try: yr,val = int(float(row.get("core_metric_variable",row.get("year","")))),float(row.get("value",""))
        except: continue
        if yr < 2020 or yr > 2055: continue
        key = (td,sn,yr,mn)
        if key in seen: continue
        seen.add(key); rows.append((td,sn,yr,mn,val,row.get("units",""),today))
    if rows: conn.executemany("INSERT OR REPLACE INTO nrel_cost_curves (technology,scenario,year,metric,value,unit,fetched_date) VALUES (?,?,?,?,?,?,?)", rows); conn.commit(); print(f"    Loaded {len(rows)} NREL points")
    return _nrel_summary()

def _nrel_summary():
    L = "metric='LCOE' AND scenario='Moderate'"
    cl = query(f"SELECT technology,scenario,value,unit FROM nrel_cost_curves WHERE {L} AND year=2025 ORDER BY value ASC")
    xo = []; nl = query(f"SELECT year,MIN(value) as value FROM nrel_cost_curves WHERE technology='Nuclear' AND {L} GROUP BY year ORDER BY year")
    if nl:
        nd = {r["year"]:r["value"] for r in nl}
        for t in ["Utility Solar","Onshore Wind","Solar + Storage"]:
            for r in (query(f"SELECT year,MIN(value) as value FROM nrel_cost_curves WHERE technology=? AND {L} GROUP BY year ORDER BY year",(t,)) or []):
                if nd.get(r["year"]) and r["value"] < nd[r["year"]]: xo.append({"technology":t,"crossover_year":r["year"],"tech_lcoe":r["value"],"nuclear_lcoe":nd[r["year"]]}); break
    return {"current_lcoe":cl or [],"lcoe_trajectory":query(f"SELECT technology,year,value FROM nrel_cost_curves WHERE {L} AND year IN (2025,2030,2035,2040,2050) ORDER BY technology,year") or [],
        "capex_trend":query("SELECT technology,year,value FROM nrel_cost_curves WHERE metric IN ('CAPEX','OCC') AND scenario='Moderate' AND year IN (2025,2030,2040) ORDER BY technology,year") or [],
        "crossovers":xo,"tech_count":len(set(r["technology"] for r in (cl or [])))}

def fetch_energy_legislation():
    if not CONGRESS_API_KEY: return {"error":"no_api_key","bills":[]}
    _ensure_tables(); conn = get_conn()
    if _fresh("SELECT MAX(fetched_date) as d FROM energy_legislation WHERE congress=?",(CURRENT_CONGRESS,)): return _leg_summary()
    all_bills = []; ekw = "energy power electric grid nuclear solar wind gas oil petroleum pipeline utility renewable clean carbon emission climate battery storage hydrogen geothermal coal lng ferc interconnection transmission rate tariff".split()+["critical mineral"]
    for bt in ["hr","s"]:
        off = 0
        while off < 5000:
            try:
                resp = requests.get(f"{CONGRESS_API_BASE}/bill/{CURRENT_CONGRESS}/{bt}",params={"api_key":CONGRESS_API_KEY,"format":"json","limit":250,"offset":off,"sort":"updateDate+desc"},timeout=30)
                resp.raise_for_status(); bills = resp.json().get("bills",[])
                if not bills: break
                for b in bills:
                    tl = (b.get("title") or "").lower()
                    if any(k in tl for k in ekw):
                        all_bills.append({"bill_id":f"{bt}{b.get('number','')}-{CURRENT_CONGRESS}","congress":CURRENT_CONGRESS,"bill_type":bt.upper(),"bill_number":b.get("number"),"title":b.get("title",""),"introduced_date":b.get("introducedDate",""),"latest_action":b.get("latestAction",{}).get("text",""),"latest_action_date":b.get("latestAction",{}).get("actionDate",""),"sponsor":"","cosponsor_count":0})
                if len(bills) < 250: break
                off += 250; time.sleep(0.5)
            except Exception as e: print(f"    Congress API error: {e}"); break
    if all_bills:
        scored = _score_leg(all_bills[:50]); today = date.today().isoformat()
        rows = [(b["bill_id"],b["congress"],b["bill_type"],b["bill_number"],b["title"],b["introduced_date"],b["latest_action"],b["latest_action_date"],b.get("sponsor",""),b.get("cosponsor_count",0),json.dumps(b.get("subjects",[])),b.get("status","introduced"),b.get("energy_relevance_score",0),json.dumps(b.get("affected_sectors",[])),json.dumps(b.get("affected_tickers",[])),b.get("summary",""),today) for b in scored]
        conn.executemany("INSERT OR REPLACE INTO energy_legislation (bill_id,congress,bill_type,bill_number,title,introduced_date,latest_action,latest_action_date,sponsor,cosponsor_count,subjects,status,energy_relevance_score,affected_sectors,affected_tickers,summary,fetched_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows); conn.commit()
    return _leg_summary()

def _score_leg(bills):
    if not GEMINI_API_KEY or not bills:
        for b in bills:
            s,tl = 0,b["title"].lower()
            for kws,pts in [(["nuclear","grid","transmission","interconnection"],40),(["solar","wind","renewable","clean energy"],30),(["tariff","lng","oil","gas"],25)]:
                if any(k in tl for k in kws): s += pts
            if "tax credit" in tl or "incentive" in tl: s += 35
            b.update({"energy_relevance_score":min(100,s),"affected_sectors":[],"affected_tickers":[]})
        return bills
    bt = "\n".join(f"[{b['bill_id']}] {b['title'][:150]} -- {b['latest_action'][:80]}" for b in bills[:30])
    try:
        resp = requests.post(f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",headers={"Content-Type":"application/json"},params={"key":GEMINI_API_KEY},
            json={"contents":[{"role":"user","parts":[{"text":f"Classify energy bills for stock impact.\nBILLS:\n{bt}\nJSON array: [{{\"bill_id\":\"...\",\"relevance\":0-100,\"sectors\":[...],\"tickers\":[...],\"summary\":\"...\"}}]. Return ONLY JSON."}]}],"generationConfig":{"temperature":0.1,"maxOutputTokens":4096,"thinkingConfig":{"thinkingBudget":0}}},timeout=60)
        resp.raise_for_status(); text = "\n".join(p["text"] for p in resp.json()["candidates"][0]["content"]["parts"] if "text" in p and not p.get("thought"))
        m = re.search(r'\[.*\]',text,re.DOTALL)
        if m:
            sm = {s["bill_id"]:s for s in json.loads(m.group())}
            for b in bills:
                if b["bill_id"] in sm: s = sm[b["bill_id"]]; b.update({"energy_relevance_score":s.get("relevance",0),"affected_sectors":s.get("sectors",[]),"affected_tickers":s.get("tickers",[]),"summary":s.get("summary","")})
    except Exception as e:
        print(f"    Gemini failed: {e}")
        for b in bills:
            if "energy_relevance_score" not in b: b.update({"energy_relevance_score":0,"affected_sectors":[],"affected_tickers":[]})
    return bills

def _leg_summary():
    hi = query("SELECT bill_id,title,energy_relevance_score,affected_sectors,affected_tickers,latest_action,latest_action_date,summary FROM energy_legislation WHERE congress=? AND energy_relevance_score>=30 ORDER BY energy_relevance_score DESC LIMIT 20",(CURRENT_CONGRESS,))
    for b in (hi or []):
        for f in ["affected_sectors","affected_tickers"]:
            try: b[f] = json.loads(b[f]) if b[f] else []
            except Exception: b[f] = []
    rc = query("SELECT COUNT(*) as cnt,MAX(latest_action_date) as ld FROM energy_legislation WHERE congress=? AND latest_action_date>=date('now','-30 days')",(CURRENT_CONGRESS,))
    tc = (query("SELECT COUNT(*) as cnt FROM energy_legislation WHERE congress=?",(CURRENT_CONGRESS,)) or [{"cnt":0}])[0]["cnt"]
    return {"high_impact_bills":hi or [],"total_bills":tc,"recent_activity_30d":rc[0]["cnt"] if rc else 0,"last_action_date":rc[0]["ld"] if rc else None}

def generate_regulatory_signals():
    _ensure_tables(); sigs = []; today = date.today().isoformat(); conn = get_conn()
    def _ms(src,st,h,d,sec,tk,sc): return {"date":today,"source":src,"signal_type":st,"headline":h,"detail":d,"affected_sectors":json.dumps(sec),"affected_tickers":json.dumps(tk),"impact_score":sc}
    qs = query("SELECT iso,fuel_type,active_count,active_mw FROM interconnection_queue_summary WHERE date=(SELECT MAX(date) FROM interconnection_queue_summary) ORDER BY active_mw DESC")
    if qs:
        tot = sum(r["active_mw"] or 0 for r in qs)
        def _fm(f): return sum(r["active_mw"] or 0 for r in qs if r["fuel_type"]==f)
        smw,nmw,bmw = _fm("Solar"),_fm("Nuclear"),_fm("Battery Storage")
        if tot>0 and smw/tot>0.5: sigs.append(_ms("interconnection_queue","solar_queue_dominance",f"Solar dominates at {smw/tot*100:.0f}%",f"{smw:,.0f}/{tot:,.0f} MW",["solar","utilities"],QUEUE_TICKERS.get("Solar",[]),60))
        if nmw>5000: sigs.append(_ms("interconnection_queue","nuclear_pipeline_growing",f"Nuclear: {nmw:,.0f} MW",f"{nmw:,.0f} MW seeking connection",["nuclear","utilities"],QUEUE_TICKERS.get("Nuclear",[]),75))
        if bmw>50000: sigs.append(_ms("interconnection_queue","battery_storage_surge",f"Battery: {bmw:,.0f} MW","Massive storage buildout",["storage","utilities"],QUEUE_TICKERS.get("Battery Storage",[]),65))
    lcoe = query("SELECT technology,value FROM nrel_cost_curves WHERE metric='LCOE' AND scenario='Moderate' AND year=2025 ORDER BY value ASC")
    if lcoe and len(lcoe)>=2: sigs.append(_ms("nrel_atb","cost_leadership",f"{lcoe[0]['technology']} cheapest at ${lcoe[0]['value']:.0f}/MWh","NREL ATB 2025",["energy","utilities"],[],55))
    for b in (query("SELECT bill_id,title,energy_relevance_score,affected_tickers FROM energy_legislation WHERE congress=? AND energy_relevance_score>=60 ORDER BY energy_relevance_score DESC LIMIT 5",(CURRENT_CONGRESS,)) or []):
        try: tk = json.loads(b["affected_tickers"]) if b["affected_tickers"] else []
        except Exception: tk = []
        sigs.append(_ms("congress","high_impact_legislation",f"[{b['bill_id']}] {b['title'][:120]}",f"Relevance: {b['energy_relevance_score']}/100",["energy","utilities"],tk,b["energy_relevance_score"]))
    if sigs:
        conn.executemany("INSERT OR REPLACE INTO energy_regulatory_signals (date,source,signal_type,headline,detail,affected_sectors,affected_tickers,impact_score) VALUES (?,?,?,?,?,?,?,?)",
            [(s["date"],s["source"],s["signal_type"],s["headline"],s["detail"],s["affected_sectors"],s["affected_tickers"],s["impact_score"]) for s in sigs]); conn.commit()
    return sigs

def run():
    pa = argparse.ArgumentParser(); pa.add_argument("--queues",action="store_true"); pa.add_argument("--costs",action="store_true")
    pa.add_argument("--regulatory",action="store_true"); pa.add_argument("--all",action="store_true"); pa.add_argument("--signals",action="store_true")
    a = pa.parse_args()
    if not any([a.queues,a.costs,a.regulatory,a.all,a.signals]): a.all = True
    init_db(); _ensure_tables()
    print(f"\n{'='*60}\n  ENERGY INFRASTRUCTURE INTELLIGENCE\n{'='*60}")
    if a.all or a.queues:
        qd = fetch_interconnection_queues()
        if "error" not in qd: print(f"    {qd.get('total_projects',0):,} projects, {qd.get('total_mw',0):,.0f} MW")
    if a.all or a.costs:
        for r in (fetch_nrel_cost_curves().get("current_lcoe") or [])[:5]: print(f"    {r['technology']:20s} ${r['value']:.0f}/MWh")
    if a.all or a.regulatory:
        ld = fetch_energy_legislation(); print(f"    {ld.get('total_bills',0)} bills, {len(ld.get('high_impact_bills',[]))} high-impact")
    if a.all or a.signals:
        for s in generate_regulatory_signals(): print(f"    [{s['impact_score']:.0f}] {s['headline'][:100]}")
    print(f"{'='*60}")

if __name__ == "__main__": run()
