"""Energy Physical Flows — physical market data ingestion (Phase 1.5d).
5 pillars: GIE EU Gas Storage, ENTSO-G Flows, CFTC CoT, EIA LNG, EIA Storage Surprise."""
import logging, os, sys, time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import requests
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
from tools.config import (EIA_API_KEY, GIE_REFRESH_HOURS, GIE_TIGHT_FILL_PCT,
    ENTSO_REFRESH_HOURS, COT_REFRESH_DAYS, COT_CONTRACTS, COT_EXTREME_PERCENTILE,
    LNG_REFRESH_DAYS, LNG_TERMINAL_CAPACITIES_BCFD)
from tools.db import get_conn, init_db, query
logger = logging.getLogger(__name__)
GIE_API, ENTSO_API = "https://agsi.gie.eu/api", "https://transparency.entsog.eu/api/v1"
CFTC_API, EIA_LNG_API = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json", "https://api.eia.gov/v2/natural-gas/move/lngexport/data/"
GIE_API_KEY = os.getenv("GIE_API_KEY", "")
SURPRISE_SERIES = {"crude": "PET.WCESTUS1.W", "natgas": "NG.NW2_EPG0_SWO_R48_BCF.W", "gasoline": "PET.WGTSTUS1.W", "distillate": "PET.WDISTUS1.W"}
LNG_TERMINAL_ALIASES = {"Sabine Pass": "SABINE_PASS", "Corpus Christi": "CORPUS_CHRISTI", "Freeport": "FREEPORT", "Cameron": "CAMERON", "Elba Island": "ELBA_ISLAND", "Cove Point": "COVE_POINT"}

DDL = [
    """CREATE TABLE IF NOT EXISTS eu_gas_storage (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, country TEXT NOT NULL, storage_twh REAL, capacity_twh REAL, fill_pct REAL, injection_withdrawal_gwh REAL, vs_5yr_avg_pct REAL, status TEXT, UNIQUE(date, country))""",
    """CREATE TABLE IF NOT EXISTS entso_gas_flows (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, point_key TEXT NOT NULL, point_label TEXT, from_country TEXT, to_country TEXT, flow_gcal REAL, nomination_gcal REAL, capacity_gcal REAL, utilization_pct REAL, UNIQUE(date, point_key))""",
    """CREATE TABLE IF NOT EXISTS cot_energy_positions (id INTEGER PRIMARY KEY AUTOINCREMENT, report_date TEXT NOT NULL, market TEXT NOT NULL, contract_code TEXT, managed_money_long INTEGER, managed_money_short INTEGER, net_position INTEGER, open_interest INTEGER, net_pct_oi REAL, net_percentile REAL, signal TEXT, UNIQUE(report_date, market))""",
    """CREATE TABLE IF NOT EXISTS lng_terminal_utilization (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT NOT NULL, terminal TEXT NOT NULL, exports_bcf REAL, capacity_bcfd REAL, utilization_pct REAL, mom_change_pct REAL, UNIQUE(period, terminal))""",
    """CREATE TABLE IF NOT EXISTS eia_storage_surprise (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, commodity TEXT NOT NULL, actual_change REAL, seasonal_expectation REAL, surprise REAL, surprise_zscore REAL, surprise_pct REAL, direction TEXT, UNIQUE(date, commodity))""",
]

def _init_tables():
    conn = get_conn()
    for stmt in DDL: conn.execute(stmt)
    conn.commit(); conn.close()

def _needs_refresh(table, date_col, max_age_hours):
    rows = query(f"SELECT MAX({date_col}) AS last FROM {table}")
    if not rows or not rows[0]["last"]: return True
    try:
        last_dt = datetime.strptime(str(rows[0]["last"])[:10], "%Y-%m-%d")
        return (datetime.utcnow() - last_dt).total_seconds() / 3600 >= max_age_hours
    except Exception: return True

def _fetch_gie_storage(days_back=60):
    end_date = date.today(); start_date = end_date - timedelta(days=days_back)
    params = {"type": "EU", "from": start_date.strftime("%Y-%m-%d"), "to": end_date.strftime("%Y-%m-%d"), "size": 500}
    headers = {"x-key": GIE_API_KEY} if GIE_API_KEY else {}
    try:
        resp = requests.get(GIE_API, params=params, headers=headers, timeout=20)
        resp.raise_for_status(); return resp.json().get("data", [])
    except Exception as e: logger.warning(f"GIE API failed: {e}"); return []

def _persist_gie_storage(rows):
    conn = get_conn(); c = conn.cursor(); saved = 0
    for row in rows:
        try:
            country = row.get("short") or row.get("code") or "EU"
            gas_date = str(row.get("gasDayStart", ""))[:10]
            fill_pct = float(row.get("full", 0) or 0) * 100
            storage_twh = float(row.get("gasInStorage", 0) or 0)
            capacity_twh = float(row.get("workingGasVolume", 0) or 0)
            net_flow = float(row.get("injection", 0) or 0) - float(row.get("withdrawal", 0) or 0)
            if not gas_date or fill_pct == 0: continue
            month = gas_date[5:7] if len(gas_date) >= 7 else ""
            vs_5yr = None
            if month:
                r = c.execute("SELECT AVG(fill_pct) FROM eu_gas_storage WHERE country=? AND substr(date,6,2)=? AND date<? AND date>=date(?,'-5 years')",
                    (country, month, gas_date, gas_date)).fetchone()
                if r and r[0] is not None: vs_5yr = round(fill_pct - r[0], 2)
            deficit = vs_5yr if vs_5yr is not None else 0.0
            status = "comfortable" if fill_pct >= 85 or deficit >= 5 else ("normal" if fill_pct >= 70 or deficit >= -2 else ("tight" if fill_pct >= GIE_TIGHT_FILL_PCT or deficit >= -10 else "critical"))
            c.execute("INSERT OR REPLACE INTO eu_gas_storage (date,country,storage_twh,capacity_twh,fill_pct,injection_withdrawal_gwh,vs_5yr_avg_pct,status) VALUES(?,?,?,?,?,?,?,?)",
                (gas_date, country, storage_twh, capacity_twh, round(fill_pct,2), round(net_flow,1), vs_5yr, status))
            saved += 1
        except Exception as e: logger.debug(f"GIE row error: {e}")
    conn.commit(); conn.close(); return saved

def _fetch_entso_flows(days_back=14, from_country=None):
    end_dt = datetime.utcnow(); start_dt = end_dt - timedelta(days=days_back)
    params = {"indicator": "Physical Flow", "periodType": "day", "timezone": "UTC", "limit": 1000,
              "from": start_dt.strftime("%Y-%m-%d"), "to": end_dt.strftime("%Y-%m-%d")}
    if from_country: params["fromCountryLabel"] = from_country
    try:
        resp = requests.get(f"{ENTSO_API}/operationalData", params=params, timeout=25)
        resp.raise_for_status(); return resp.json().get("operationalData", [])
    except Exception as e: logger.warning(f"ENTSO-G flows (from={from_country}) failed: {e}"); return []

def _persist_entso_flows(rows):
    conn = get_conn(); c = conn.cursor(); saved = 0
    for row in rows:
        try:
            pk = str(row.get("pointKey", "")); fd = str(row.get("periodFrom", ""))[:10]
            if not pk or not fd: continue
            flow = float(row.get("value", 0) or 0); cap = float(row.get("capacityValue", 0) or 0)
            util = round(flow / cap * 100, 1) if cap > 0 else None
            c.execute("INSERT OR REPLACE INTO entso_gas_flows (date,point_key,point_label,from_country,to_country,flow_gcal,nomination_gcal,capacity_gcal,utilization_pct) VALUES(?,?,?,?,?,?,?,?,?)",
                (fd, pk, str(row.get("pointLabel","")), str(row.get("fromCountryLabel","")),
                 str(row.get("toCountryLabel","")), round(flow,1),
                 round(float(row.get("renominationValue") or flow),1), round(cap,1), util))
            saved += 1
        except Exception as e: logger.debug(f"ENTSO row error: {e}")
    conn.commit(); conn.close(); return saved

def _fetch_cot_positions():
    results = []
    for mkt, code in COT_CONTRACTS.items():
        try:
            resp = requests.get(CFTC_API, params={"$where": f"contract_market_code='{code}'",
                "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": 104}, timeout=20)
            resp.raise_for_status()
            for r in resp.json(): r["_market"] = mkt; r["_contract_code"] = code; results.append(r)
            time.sleep(0.4)
        except Exception as e: logger.warning(f"CFTC {mkt}: {e}")
    return results

def _persist_cot_positions(rows):
    """Store commercial hedger (prod_merc) net positions.

    Producers/merchants are the informed side in commodity futures — they have
    physical exposure and hedge selectively. High net_percentile = producers are
    less hedged than historical norm = bullish conviction on price direction.
    Uses prod_merc_positions_long/short from CFTC disaggregated dataset (72hh-3qpy).
    """
    conn = get_conn(); c = conn.cursor(); saved = 0
    market_nets = defaultdict(list)
    for row in rows:
        try:
            l = int(row.get("prod_merc_positions_long",0) or 0); s = int(row.get("prod_merc_positions_short",0) or 0)
            oi = int(row.get("open_interest_all",1) or 1)
            market_nets[row["_market"]].append((l-s)/oi*100 if oi>0 else 0)
        except Exception: pass
    for row in rows:
        try:
            mkt = row["_market"]; rd = str(row.get("report_date_as_yyyy_mm_dd",""))[:10]
            if not rd: continue
            l = int(row.get("prod_merc_positions_long",0) or 0); s = int(row.get("prod_merc_positions_short",0) or 0)
            oi = int(row.get("open_interest_all",1) or 1)
            net = l - s; net_pct = round(net/oi*100, 2) if oi > 0 else 0
            hist = market_nets[mkt]
            pctl = round(sum(1 for h in hist if h < net_pct) / len(hist) * 100, 1) if hist else 50.0
            sig = "extreme_long" if pctl >= COT_EXTREME_PERCENTILE else ("extreme_short" if pctl <= (100 - COT_EXTREME_PERCENTILE) else "neutral")
            c.execute("INSERT OR REPLACE INTO cot_energy_positions (report_date,market,contract_code,managed_money_long,managed_money_short,net_position,open_interest,net_pct_oi,net_percentile,signal) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (rd, mkt, row["_contract_code"], l, s, net, oi, net_pct, pctl, sig))
            saved += 1
        except Exception as e: logger.debug(f"CoT row error: {e}")
    conn.commit(); conn.close(); return saved

def _fetch_eia_lng_exports():
    if not EIA_API_KEY: logger.warning("EIA_API_KEY not set; LNG skipped"); return []
    try:
        resp = requests.get(EIA_LNG_API, params={"api_key": EIA_API_KEY, "frequency": "monthly",
            "data[0]": "value", "sort[0][column]": "period", "sort[0][direction]": "desc", "offset": 0, "length": 120}, timeout=20)
        resp.raise_for_status(); return resp.json().get("response", {}).get("data", [])
    except Exception as e: logger.warning(f"EIA LNG API failed: {e}"); return []

def _persist_lng_utilization(rows):
    conn = get_conn(); c = conn.cursor(); saved = 0; tp = defaultdict(lambda: defaultdict(float))
    for row in rows:
        try:
            period = str(row.get("period",""))[:7]; val = float(row.get("value",0) or 0)
            desc = str(row.get("description", row.get("seriesId", "")))
            for tname, tkey in LNG_TERMINAL_ALIASES.items():
                if tname.lower() in desc.lower(): tp[tkey][period] += val; break
        except Exception: pass
    for tkey, pd in tp.items():
        periods = sorted(pd.keys(), reverse=True); cap = LNG_TERMINAL_CAPACITIES_BCFD.get(tkey, 1.0)
        for i, p in enumerate(periods):
            exp = pd[p]; util = min(110.0, exp/30.4/cap*100)
            prev = pd.get(periods[i+1], 0) if i+1 < len(periods) else 0
            mom = (exp - prev) / prev * 100 if prev > 0 else 0.0
            try:
                c.execute("INSERT OR REPLACE INTO lng_terminal_utilization (period,terminal,exports_bcf,capacity_bcfd,utilization_pct,mom_change_pct) VALUES(?,?,?,?,?,?)",
                    (p, tkey, round(exp,3), cap, round(util,1), round(mom,1))); saved += 1
            except Exception as e: logger.debug(f"LNG error {tkey}/{p}: {e}")
    conn.commit(); conn.close(); return saved

def _compute_storage_surprises():
    conn = get_conn(); c = conn.cursor(); saved = 0
    for commodity, series_id in SURPRISE_SERIES.items():
        rows = c.execute("SELECT date, value FROM energy_eia_enhanced WHERE series_id=? ORDER BY date ASC", (series_id,)).fetchall()
        dated = [(r[0], r[1]) for r in rows if r[1] is not None]
        if len(dated) < 8: continue
        changes = [(dated[i][0], dated[i][1] - dated[i-1][1]) for i in range(1, len(dated))]
        for chg_date, actual_change in changes[-12:]:
            try: wk = datetime.strptime(chg_date, "%Y-%m-%d").isocalendar()[1]
            except ValueError: continue
            same_week = [chg for dt, chg in changes if dt < chg_date and datetime.strptime(dt, "%Y-%m-%d").isocalendar()[1] == wk]
            if len(same_week) < 3: continue
            seasonal_exp = sum(same_week) / len(same_week); surprise = actual_change - seasonal_exp
            all_surp = []
            for dt, chg in changes:
                if dt >= chg_date: continue
                try:
                    w2 = datetime.strptime(dt, "%Y-%m-%d").isocalendar()[1]
                    ps = [c2 for d2, c2 in changes if d2 < dt and datetime.strptime(d2, "%Y-%m-%d").isocalendar()[1] == w2]
                    if ps: all_surp.append(chg - sum(ps)/len(ps))
                except Exception: pass
            zscore = 0.0
            if len(all_surp) >= 5:
                mu = sum(all_surp)/len(all_surp); std = (sum((s-mu)**2 for s in all_surp)/len(all_surp))**0.5
                if std > 0: zscore = round((surprise-mu)/std, 3)
            cur = dated[-1][1] if dated else 1.0; spct = round(surprise/cur*100, 4) if cur else 0
            direction = "bullish_surprise" if surprise < -1.5 and zscore < -0.5 else ("bearish_surprise" if surprise > 1.5 and zscore > 0.5 else "inline")
            try:
                c.execute("INSERT OR REPLACE INTO eia_storage_surprise (date,commodity,actual_change,seasonal_expectation,surprise,surprise_zscore,surprise_pct,direction) VALUES(?,?,?,?,?,?,?,?)",
                    (chg_date, commodity, round(actual_change,3), round(seasonal_exp,3), round(surprise,3), zscore, spct, direction))
                saved += 1
            except Exception as e: logger.debug(f"Surprise error: {e}")
    conn.commit(); conn.close(); return saved

def get_eu_storage_signal():
    rows = query("SELECT country,fill_pct,vs_5yr_avg_pct,status FROM eu_gas_storage WHERE date=(SELECT MAX(date) FROM eu_gas_storage WHERE country='EU') AND country IN ('EU','DE','FR','NL','IT','AT') ORDER BY country")
    if not rows: return {"score": 50.0, "fill_pct": None, "status": "unknown"}
    eu = next((r for r in rows if r["country"] == "EU"), rows[0])
    fill = eu["fill_pct"] or 50.0; vs = eu["vs_5yr_avg_pct"] or 0.0
    score = max(0, min(100, min(100, fill*1.05) + max(-30, min(30, vs*2))))
    return {"score": round(score,1), "fill_pct": round(fill,1), "vs_5yr": round(vs,1),
            "status": eu["status"] or "normal", "countries": {r["country"]: r["fill_pct"] for r in rows}}

def get_norway_flow_signal():
    rows = query("SELECT date,SUM(flow_gcal) AS total_flow,SUM(capacity_gcal) AS total_cap FROM entso_gas_flows WHERE from_country='Norway' AND date>=date('now','-30 days') GROUP BY date ORDER BY date DESC LIMIT 30")
    if not rows or len(rows) < 5: return {"score": 50.0, "utilization_pct": None}
    recent = [r["total_flow"]/r["total_cap"]*100 for r in rows[:7] if r["total_cap"] and r["total_cap"]>0]
    hist = [r["total_flow"]/r["total_cap"]*100 for r in rows if r["total_cap"] and r["total_cap"]>0]
    if not recent or not hist: return {"score": 50.0, "utilization_pct": None}
    ar = sum(recent)/len(recent); ah = sum(hist)/len(hist)
    return {"score": round(max(0, min(100, min(100, ar*1.1) + (ar-ah)*0.5)),1), "utilization_pct": round(ar,1), "trend_vs_30d": round(ar-ah,1)}

def get_cot_signal(market="NAT_GAS_HH"):
    """Commercial hedger COT signal. High percentile = producers less hedged = bullish.

    Score direction: percentile maps directly to score (NOT inverted).
    Commercial extreme_long (pctl=90) → score=90 (bullish).
    Commercial extreme_short (pctl=10) → score=10 (heavy hedging = bearish).
    This is the OPPOSITE of managed money where extreme_long = crowded = bearish.
    """
    rows = query("SELECT report_date,net_percentile,signal,net_pct_oi FROM cot_energy_positions WHERE market=? ORDER BY report_date DESC LIMIT 4", [market])
    if not rows: return {"score": 50.0, "percentile": None, "signal": "no_data"}
    p = rows[0]["net_percentile"] or 50.0; sig = rows[0]["signal"] or "neutral"
    # Commercial: high percentile = bullish (direct mapping, not inverted)
    score = max(0, min(100, p))
    return {"score": round(score,1), "percentile": round(p,1), "signal": sig, "net_pct_oi": rows[0]["net_pct_oi"]}

def get_storage_surprise_signal():
    rows = query("SELECT commodity,direction,surprise_zscore FROM eia_storage_surprise WHERE date>=date('now','-14 days') ORDER BY date DESC")
    if not rows: return {"score": 50.0, "commodities": {}}
    weights = {"crude": 0.40, "natgas": 0.35, "gasoline": 0.15, "distillate": 0.10}
    seen = {}
    for r in rows:
        if r["commodity"] not in seen: seen[r["commodity"]] = r
    ws = 0.0; tw = 0.0; detail = {}
    for comm, r in seen.items():
        w = weights.get(comm, 0.10); z = r["surprise_zscore"] or 0.0; s = max(0, min(100, 50 - z*20))
        ws += s*w; tw += w; detail[comm] = {"score": round(s,1), "zscore": round(z,2), "direction": r["direction"]}
    return {"score": round(ws/tw, 1) if tw > 0 else 50.0, "commodities": detail}

def get_lng_utilization_signal():
    rows = query("SELECT terminal,utilization_pct,mom_change_pct FROM lng_terminal_utilization WHERE period=(SELECT MAX(period) FROM lng_terminal_utilization)")
    if not rows: return {"score": 50.0, "avg_utilization": None}
    utils = [r["utilization_pct"] for r in rows if r["utilization_pct"] is not None]
    moms = [r["mom_change_pct"] for r in rows if r["mom_change_pct"] is not None]
    if not utils: return {"score": 50.0, "avg_utilization": None}
    au = sum(utils)/len(utils); am = sum(moms)/len(moms) if moms else 0
    score = max(0, min(100, min(100, au*1.05) + max(-20, min(20, am*0.5))))
    return {"score": round(score,1), "avg_utilization": round(au,1), "mom_change_pct": round(am,1),
            "by_terminal": {r["terminal"]: r["utilization_pct"] for r in rows}}

def run():
    init_db(); _init_tables(); results = {}
    for label, table, dcol, hrs, fetch_fn, persist_fn, kw in [
        ("EU gas storage", "eu_gas_storage", "date", GIE_REFRESH_HOURS, lambda: _fetch_gie_storage(60), _persist_gie_storage, "gie"),
        ("ENTSO-G flows", "entso_gas_flows", "date", ENTSO_REFRESH_HOURS, None, None, "entso"),
        ("CoT positions", "cot_energy_positions", "report_date", COT_REFRESH_DAYS*24, _fetch_cot_positions, _persist_cot_positions, "cot"),
        ("LNG terminals", "lng_terminal_utilization", "period", LNG_REFRESH_DAYS*24, _fetch_eia_lng_exports, _persist_lng_utilization, "lng"),
    ]:
        if kw == "entso":
            if _needs_refresh(table, dcol, hrs):
                print(f"  Fetching ENTSO-G cross-border gas flows...")
                eu = _fetch_entso_flows(14); no = _fetch_entso_flows(14, "Norway")
                n = _persist_entso_flows(eu + [r for r in no if r not in eu])
                print(f"  -> ENTSO-G flows: {n} records"); results["entso"] = n
            else: print(f"  -> ENTSO-G flows: up to date"); results["entso"] = 0
        elif _needs_refresh(table, dcol, hrs):
            print(f"  Fetching {label}..."); raw = fetch_fn()
            n = persist_fn(raw); print(f"  -> {label}: {n} records"); results[kw] = n
        else: print(f"  -> {label}: up to date"); results[kw] = 0
    print("  Computing EIA storage surprise model...")
    results["surprise"] = _compute_storage_surprises()
    print(f"  -> Storage surprises: {results['surprise']} computed")
    eu_s, no_s = get_eu_storage_signal(), get_norway_flow_signal()
    cot_s, sup_s, lng_s = get_cot_signal("NAT_GAS_HH"), get_storage_surprise_signal(), get_lng_utilization_signal()
    print(f"\n  Physical Flow Signals:")
    print(f"    EU Storage  : {eu_s['score']:5.1f}  fill={eu_s.get('fill_pct','?')}%  vs5yr={eu_s.get('vs_5yr','?')}%  [{eu_s.get('status','?')}]")
    print(f"    Norway Flow : {no_s['score']:5.1f}  util={no_s.get('utilization_pct','?')}%")
    print(f"    CoT HH Gas  : {cot_s['score']:5.1f}  pctl={cot_s.get('percentile','?')}  signal={cot_s.get('signal','?')}")
    print(f"    Stor Surprise: {sup_s['score']:5.1f}")
    print(f"    LNG Util    : {lng_s['score']:5.1f}  avg={lng_s.get('avg_utilization','?')}%")
    return results

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"); run()
