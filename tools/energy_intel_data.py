"""Energy Intelligence Data Ingestion — physical supply-demand fundamentals.
Sources: EIA API (enhanced), JODI (jodidata.org), UN Comtrade, existing macro_indicators."""
import sys, math, logging, time, json
from datetime import date, datetime, timedelta
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import (EIA_API_KEY, SERPER_API_KEY, GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    ENERGY_EIA_ENHANCED_SERIES, ENERGY_SEASONAL_LOOKBACK_YEARS, ENERGY_JODI_COUNTRIES,
    ENERGY_JODI_MAX_LAG_DAYS, ENERGY_COMTRADE_REFRESH_DAYS)
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)
EIA_API_BASE = "https://api.eia.gov/v2"

def _fetch_eia_series(series_id, length=260):
    if not EIA_API_KEY: return []
    try:
        resp = requests.get(f"{EIA_API_BASE}/seriesid/{series_id}",
            params={"api_key":EIA_API_KEY,"sort[0][column]":"period","sort[0][direction]":"desc","length":length},
            timeout=15, verify=False)
        if resp.status_code != 200: return []
        return [(d["period"], float(d["value"])) for d in resp.json().get("response",{}).get("data",[]) if d.get("value") is not None]
    except Exception as e:
        logger.warning(f"EIA fetch failed for {series_id}: {e}"); return []

def _fetch_enhanced_eia():
    print("  Fetching enhanced EIA series..."); rows = []
    for series_id, description, category in ENERGY_EIA_ENHANCED_SERIES:
        values = _fetch_eia_series(series_id, length=260)
        if not values: continue
        logger.info(f"  {description}: {len(values)} obs")
        for i, (dt, val) in enumerate(values):
            wow = (val - values[i+1][1]) if i+1 < len(values) else None
            yoy = (val - values[i+52][1]) if i+52 < len(values) else None
            rows.append((series_id, dt, category, description, val, wow, yoy))
        time.sleep(0.3)
    if rows:
        upsert_many("energy_eia_enhanced",
            ["series_id","date","category","description","value","wow_change","yoy_change"], rows)
    print(f"    Saved {len(rows)} enhanced EIA data points"); return len(rows)

def _compute_seasonal_norms():
    print("  Computing seasonal norms...")
    all_series = {s[0] for s in ENERGY_EIA_ENHANCED_SERIES}
    all_series.update(["PET.WCESTUS1.W","PET.WGTSTUS1.W","PET.WDISTUS1.W","PET.WCRFPUS2.W","PET.WPULEUS3.W"])
    today = date.today()
    cutoff = (today - timedelta(days=ENERGY_SEASONAL_LOOKBACK_YEARS*365+30)).isoformat()
    norm_rows = []
    for series_id in all_series:
        values = query("SELECT date,value FROM energy_eia_enhanced WHERE series_id=? AND date>=? ORDER BY date",
                        [series_id, cutoff])
        if not values:
            values = query("SELECT date,value FROM macro_indicators WHERE indicator_id=? AND date>=? ORDER BY date",
                           [series_id, cutoff])
        if len(values) < 20: continue
        by_week: dict[int, list[float]] = {}
        for row in values:
            try:
                woy = datetime.strptime(row["date"][:10], "%Y-%m-%d").isocalendar()[1]
                by_week.setdefault(woy, []).append(row["value"])
            except (ValueError, TypeError): continue
        for woy, vals in by_week.items():
            if len(vals) < 2: continue
            avg = sum(vals)/len(vals)
            std = (sum((v-avg)**2 for v in vals)/len(vals))**0.5
            norm_rows.append((series_id, woy, avg, std, min(vals), max(vals), len(vals), today.isoformat()))
    if norm_rows:
        upsert_many("energy_seasonal_norms",
            ["series_id","week_of_year","avg_value","std_value","min_value","max_value","sample_count","last_updated"],
            norm_rows)
    print(f"    Norms: {len(all_series)} series, {len(norm_rows)} week-buckets")

def _jodi_is_fresh():
    rows = query("SELECT MAX(last_updated) as lu FROM energy_jodi_data")
    if not rows or not rows[0]["lu"]: return False
    return (datetime.now() - datetime.fromisoformat(rows[0]["lu"])).days < 30

def _fetch_jodi_data():
    if _jodi_is_fresh(): print("  JODI data fresh, skipping..."); return
    if not SERPER_API_KEY or not GEMINI_API_KEY:
        print("  WARNING: SERPER/GEMINI key missing, skipping JODI"); return
    print("  Fetching JODI international oil data...")
    try:
        resp = requests.post("https://google.serper.dev/search",
            json={"q":"JODI oil world database latest monthly production demand stocks 2024 2025 2026","num":5},
            headers={"X-API-KEY":SERPER_API_KEY}, timeout=10)
        if resp.status_code != 200: return
        results = resp.json().get("organic",[])
    except Exception as e: print(f"    Serper error: {e}"); return
    context = "\n---\n".join(f"Title: {r.get('title','')}\nSnippet: {r.get('snippet','')}" for r in results[:5])
    prompt = f"""From JODI search results, extract latest monthly data for: {', '.join(ENERGY_JODI_COUNTRIES)}
Per country extract: production, demand/consumption, closing stocks, imports, exports (kbd or mb).
Return ONLY JSON array: [{{"country":"...","indicator":"production|demand|stocks|imports|exports","date":"YYYY-MM","value":12345.6,"unit":"kbd|mb"}}]
Be conservative -- only include confident numbers.
Results:\n{context}"""
    try:
        resp = requests.post(f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=60)
        if resp.status_code != 200: return
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text.startswith("```"): text = text.split("\n",1)[1]
        if text.endswith("```"): text = text[:-3]
        records = json.loads(text.strip())
    except Exception as e: print(f"    Gemini JODI error: {e}"); return
    today_str = date.today().isoformat(); rows = []
    for rec in records:
        country, indicator, dt, value, unit = rec.get("country",""), rec.get("indicator",""), rec.get("date",""), rec.get("value"), rec.get("unit","")
        if not all([country, indicator, dt, value]): continue
        prior = query("SELECT value FROM energy_jodi_data WHERE country=? AND indicator=? AND date<? ORDER BY date DESC LIMIT 1",
                       [country, indicator, dt])
        mom = (value - prior[0]["value"]) if prior else None
        yoy_target = str(int(dt[:4])-1) + dt[4:]
        yoy_rows = query("SELECT value FROM energy_jodi_data WHERE country=? AND indicator=? AND date=?",
                          [country, indicator, yoy_target])
        yoy = (value - yoy_rows[0]["value"]) if yoy_rows else None
        rows.append((country, indicator, dt, value, unit, mom, yoy, today_str))
    if rows:
        upsert_many("energy_jodi_data",
            ["country","indicator","date","value","unit","mom_change","yoy_change","last_updated"], rows)
    print(f"    Extracted {len(rows)} JODI data points")

def _comtrade_is_fresh():
    rows = query("SELECT MAX(last_updated) as lu FROM energy_trade_flows")
    if not rows or not rows[0]["lu"]: return False
    return (datetime.now() - datetime.fromisoformat(rows[0]["lu"])).days < ENERGY_COMTRADE_REFRESH_DAYS

def _fetch_comtrade_data():
    if _comtrade_is_fresh(): print("  Comtrade fresh, skipping..."); return
    print("  Fetching UN Comtrade trade flows...")
    today_str = date.today().isoformat(); rows = []
    for reporter in ["USA","CHN","IND","JPN","KOR","DEU"]:
        for hs in ["2709","2710","2711"]:
            try:
                resp = requests.get("https://comtradeapi.un.org/data/v1/get/C/M",
                    params={"reporterCode":reporter,"cmdCode":hs,"flowCode":"M,X","period":"recent","maxRecords":100}, timeout=20)
                if resp.status_code != 200: continue
                for rec in resp.json().get("data",[]):
                    rows.append((rec.get("reporterDesc",reporter), rec.get("partnerDesc","World"), hs,
                        str(rec.get("period","")), rec.get("flowDesc",""), rec.get("primaryValue"),
                        rec.get("netWgt"), today_str))
                time.sleep(1.0)
            except Exception as e:
                logger.warning(f"Comtrade failed for {reporter}/{hs}: {e}")
    if rows:
        upsert_many("energy_trade_flows",
            ["reporter","partner","commodity_code","period","trade_flow","value_usd","quantity_kg","last_updated"], rows)
    print(f"    Fetched {len(rows)} Comtrade records")

def _detect_supply_anomalies():
    print("  Detecting supply anomalies...")
    today = date.today(); wk = today.isocalendar()[1]; alerts = []
    for series_id, desc, table in [
        ("PET.WCESTUS1.W","US Crude Stocks","macro_indicators"),
        ("PET.WGTSTUS1.W","US Gasoline Stocks","macro_indicators"),
        ("PET.WDISTUS1.W","US Distillate Stocks","macro_indicators"),
        ("PET.WCESTP21.W","Cushing Crude Stocks","energy_eia_enhanced")]:
        id_col = "indicator_id" if table == "macro_indicators" else "series_id"
        latest = query(f"SELECT date,value FROM {table} WHERE {id_col}=? ORDER BY date DESC LIMIT 2", [series_id])
        if len(latest) < 2: continue
        cur, wow = latest[0]["value"], latest[0]["value"] - latest[1]["value"]
        norms = query("SELECT avg_value,std_value FROM energy_seasonal_norms WHERE series_id=? AND week_of_year=?",
                       [series_id, wk])
        if not norms or not norms[0]["std_value"]: continue
        avg, std = norms[0]["avg_value"], norms[0]["std_value"]
        z = (cur - avg) / std
        sev = "critical" if abs(z) >= 3.0 else "high" if abs(z) >= 2.0 else "medium" if abs(z) >= 1.5 else None
        if not sev: continue
        direction = "above" if z > 0 else "below"
        atype = "inventory_surplus" if z > 0 else "inventory_deficit"
        affected = ("MPC,VLO,PSX" if "Gasoline" in desc or "Distillate" in desc
                    else "OXY,COP,XOM,CVX,DVN,FANG,EOG,PXD" if "Crude" in desc else "OXY,COP,XOM,CVX")
        alerts.append((today.isoformat(), atype, series_id,
            f"{desc} is {abs(z):.1f} std {direction} seasonal (current:{cur:,.1f}, avg:{avg:,.1f}, WoW:{wow:+,.1f})",
            z, sev, affected))
    if alerts:
        with get_conn() as conn:
            conn.executemany("""INSERT OR REPLACE INTO energy_supply_anomalies
                (date,anomaly_type,series_id,description,zscore,severity,affected_tickers)
                VALUES (?,?,?,?,?,?,?)""", alerts)
    print(f"    Detected {len(alerts)} supply anomalies")

def run():
    init_db()
    if not EIA_API_KEY: print("  ERROR: EIA_API_KEY not set"); return
    print("\n  === ENERGY INTELLIGENCE DATA INGESTION ===")
    _fetch_enhanced_eia()
    _compute_seasonal_norms()
    _fetch_jodi_data()
    _fetch_comtrade_data()
    _detect_supply_anomalies()
    print("  === ENERGY DATA INGESTION COMPLETE ===\n")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
