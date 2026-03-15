"""Government Intelligence — 5 regulatory/labor sources into gov_intel_score (0-100). Weekly."""
import json, logging, time, traceback
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
import requests
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)
WEIGHTS = {"warn": 0.30, "osha": 0.15, "epa": 0.20, "fcc": 0.15, "lobby": 0.20}
NEUTRAL_SCORE, MATCH_THRESHOLD, MAX_RECORDS, RATE_LIMIT_DELAY, LOOKBACK_DAYS = 50, 0.85, 500, 0.5, 90
_session = requests.Session()
_session.headers.update({"User-Agent": "DruckenmillerAlpha/1.0 (research; gov-intel)"})
RAW_COLS = ["symbol", "date", "source", "event_type", "severity", "details"]

def _should_run() -> bool:
    rows = query("SELECT MAX(date) as last_run FROM gov_intel_scores")
    if not rows or not rows[0]["last_run"]: return True
    return (date.today() - datetime.strptime(rows[0]["last_run"], "%Y-%m-%d").date()).days >= 7

def _get_universe(): return {r["symbol"]: r["name"] for r in query("SELECT symbol, name FROM stock_universe WHERE name IS NOT NULL")}
def _get_market_caps(): return {r["symbol"]: r["value"] for r in query("SELECT symbol, value FROM fundamentals WHERE metric = 'marketCap' AND value > 0")}

def _match(company_name, universe):
    if not company_name: return None
    cl = company_name.lower().strip()
    best_ticker, best_ratio = None, 0.0
    for symbol, name in universe.items():
        if not name: continue
        nl = name.lower().strip()
        if cl in nl or nl in cl: return symbol
        r = SequenceMatcher(None, cl, nl).ratio()
        if r > best_ratio: best_ratio, best_ticker = r, symbol
    return best_ticker if best_ratio >= MATCH_THRESHOLD else None

def _safe_get(url, params=None, timeout=15):
    time.sleep(RATE_LIMIT_DELAY)
    try:
        resp = _session.get(url, params=params, timeout=timeout); resp.raise_for_status(); return resp.json()
    except Exception as exc:
        logger.warning("GET %s failed: %s", url, exc); return None

def _cutoff(): return (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()

def _parse_warn_records(records, universe, cutoff, today_str):
    layoffs, raw_rows = {}, []
    for rec in records[:MAX_RECORDS]:
        company = rec.get("company_name") or rec.get("establishment_name", "")
        employees = rec.get("number_affected") or rec.get("employees_affected", 0)
        try: employees = int(employees)
        except (ValueError, TypeError): employees = 0
        ld = rec.get("effective_date") or rec.get("notice_date", "")
        if ld and ld < cutoff: continue
        ticker = _match(company, universe)
        if ticker:
            layoffs[ticker] = layoffs.get(ticker, 0) + employees
            raw_rows.append((ticker, today_str, "warn", "layoff", "high" if employees > 500 else "medium",
                json.dumps({"company": company, "employees": employees, "date": ld})))
    return layoffs, raw_rows

def _fetch_warn_scores(universe, market_caps):
    print("  [1/5] WARN Act layoff filings ...")
    today_str, cutoff = date.today().isoformat(), _cutoff()
    data = _safe_get("https://enforcedata.dol.gov/api/warn", params={"page": "0", "per_page": str(MAX_RECORDS)})
    records = data if isinstance(data, list) else (data.get("results", []) if isinstance(data, dict) else [])
    layoffs, raw_rows = _parse_warn_records(records, universe, cutoff, today_str) if records else ({}, [])
    print(f"    Parsed {len(records)} WARN records, matched {len(layoffs)} tickers")
    scores = {}
    for sym in universe:
        n = layoffs.get(sym, 0)
        if n == 0: scores[sym] = 75.0
        else:
            intensity = n / (market_caps.get(sym, 1e10) / 1e9)
            scores[sym] = 10.0 if intensity > 100 else 20.0 if intensity > 50 else 30.0 if intensity > 10 else 50.0 if intensity > 1 else 65.0
    if raw_rows: upsert_many("gov_intel_raw", RAW_COLS, raw_rows)
    return scores

def _fetch_osha_scores(universe):
    print("  [2/5] OSHA inspection logs ...")
    today_str, cutoff = date.today().isoformat(), _cutoff()
    data = _safe_get("https://enforcedata.dol.gov/api/enforcement/osha_inspection", params={"page": "0", "per_page": str(MAX_RECORDS)})
    violations_by_ticker, raw_rows = {}, []
    records = data.get("results", data.get("data", [])) if isinstance(data, dict) else (data if isinstance(data, list) else None)
    if records and isinstance(records, list):
        for rec in records[:MAX_RECORDS]:
            company, od = rec.get("establishment_name", ""), rec.get("open_date", "")
            ct, vt = rec.get("case_type", ""), rec.get("violation_type", "")
            if od and od[:10] < cutoff: continue
            ticker = _match(company, universe)
            if ticker:
                violations_by_ticker.setdefault(ticker, []).append(vt or ct)
                raw_rows.append((ticker, today_str, "osha", ct or "inspection",
                    "high" if "willful" in (vt or "").lower() else "medium",
                    json.dumps({"company": company, "date": od, "case_type": ct, "violation_type": vt})))
    scores = {}
    for sym in universe:
        viols = violations_by_ticker.get(sym, [])
        if not viols: scores[sym] = 70.0
        else:
            vl = [v.lower() for v in viols]
            scores[sym] = 10.0 if any("willful" in v or "repeat" in v for v in vl) else 30.0 if any("serious" in v for v in vl) else 50.0
    if raw_rows: upsert_many("gov_intel_raw", RAW_COLS, raw_rows)
    return scores

def _fetch_epa_scores(universe):
    print("  [3/5] EPA ECHO permits & violations ...")
    today_str = date.today().isoformat()
    data = _safe_get("https://echodata.epa.gov/echo/facility_rest_services.get_facilities",
        params={"output": "JSON", "p_act": "Y", "p_ptype": "NPD", "responseset": str(MAX_RECORDS)}, timeout=30)
    permits_by_ticker, raw_rows = {}, []
    if data and isinstance(data, dict):
        results = data.get("Results", data.get("results", {}))
        facilities = results.get("Facilities", results.get("facilities", [])) if isinstance(results, dict) else (results if isinstance(results, list) else [])
        for fac in facilities[:MAX_RECORDS]:
            name = fac.get("FacName") or fac.get("facility_name", "")
            ticker = _match(name, universe)
            if ticker:
                permits_by_ticker.setdefault(ticker, {"permits": 0, "violations": 0})["permits"] += 1
                if fac.get("CurrVioFlag") in ("Y", "1", True, 1): permits_by_ticker[ticker]["violations"] += 1
                raw_rows.append((ticker, today_str, "epa", "facility_record",
                    "high" if fac.get("CurrVioFlag") else "low", json.dumps({"name": name})))
    scores = {}
    for sym in universe:
        info = permits_by_ticker.get(sym)
        if not info: scores[sym] = NEUTRAL_SCORE
        else: scores[sym] = max(10.0, min(90.0, 60.0 + min(info["permits"] * 2, 20) - min(info["violations"] * 15, 40)))
    if raw_rows: upsert_many("gov_intel_raw", RAW_COLS, raw_rows)
    return scores

def _fetch_fcc_scores(universe):
    print("  [4/5] FCC filings ...")
    today_str, cutoff = date.today().isoformat(), _cutoff()
    data = _safe_get("https://publicapi.fcc.gov/ecfs/filings",
        params={"sort": "date_disseminated,DESC", "limit": str(MAX_RECORDS), "date_disseminated": f"[gte]{cutoff}"}, timeout=30)
    filings_by_ticker, raw_rows = {}, []
    if data and isinstance(data, dict):
        filings = data.get("filings", data.get("results", []))
        if isinstance(filings, list):
            for f in filings[:MAX_RECORDS]:
                fd = f.get("date_disseminated", "")
                for filer in (f.get("filers", []) if isinstance(f.get("filers"), list) else []):
                    name = filer.get("name", "")
                    ticker = _match(name, universe)
                    if ticker:
                        filings_by_ticker[ticker] = filings_by_ticker.get(ticker, 0) + 1
                        raw_rows.append((ticker, today_str, "fcc", "filing", "low", json.dumps({"filer": name, "date": fd})))
    scores = {}
    for sym in universe:
        c = filings_by_ticker.get(sym, 0)
        scores[sym] = NEUTRAL_SCORE if c == 0 else 80.0 if c >= 5 else 70.0 if c >= 2 else 60.0
    if raw_rows: upsert_many("gov_intel_raw", RAW_COLS, raw_rows)
    return scores

def _fetch_lobbying_scores(universe):
    print("  [5/5] Lobbying disclosures ...")
    today_str = date.today().isoformat()
    data = _safe_get("https://lda.senate.gov/api/v1/filings/",
        params={"filing_type": "Q", "page_size": str(MAX_RECORDS), "ordering": "-dt_posted"}, timeout=30)
    spend_by_ticker, raw_rows = {}, []
    if data and isinstance(data, dict):
        results = data.get("results", [])
        if isinstance(results, list):
            for f in results[:MAX_RECORDS]:
                reg = f.get("registrant", {})
                name = reg.get("name", "") if isinstance(reg, dict) else ""
                try: amount = float(f.get("income") or f.get("expenses") or 0)
                except (ValueError, TypeError): amount = 0.0
                ticker = _match(name, universe)
                if ticker:
                    spend_by_ticker[ticker] = spend_by_ticker.get(ticker, 0) + amount
                    raw_rows.append((ticker, today_str, "lobbying", "quarterly_filing", "low", json.dumps({"registrant": name, "amount": amount})))
    scores = {}
    if spend_by_ticker:
        mx = max(spend_by_ticker.values())
        for sym in universe:
            sp = spend_by_ticker.get(sym, 0)
            scores[sym] = NEUTRAL_SCORE if sp == 0 else round(55 + (sp / mx if mx > 0 else 0) * 25, 1)
    else:
        for sym in universe: scores[sym] = NEUTRAL_SCORE
    if raw_rows: upsert_many("gov_intel_raw", RAW_COLS, raw_rows)
    return scores

def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gov_intel_raw (symbol TEXT, date TEXT, source TEXT, event_type TEXT, severity TEXT, details TEXT, PRIMARY KEY (symbol, date, source, event_type));
        CREATE TABLE IF NOT EXISTS gov_intel_scores (symbol TEXT, date TEXT, gov_intel_score REAL, warn_score REAL, osha_score REAL, epa_score REAL, fcc_score REAL, lobbying_score REAL, details TEXT, PRIMARY KEY (symbol, date));
    """)
    conn.commit(); conn.close()

def run():
    init_db(); _ensure_tables()
    print("\n" + "=" * 60 + "\n  GOVERNMENT INTELLIGENCE MODULE\n" + "=" * 60)
    if not _should_run():
        print("  Skipping — last run was within 7 days\n" + "=" * 60); return
    universe = _get_universe()
    if not universe:
        print("  No stock universe found\n" + "=" * 60); return
    print(f"  Universe: {len(universe)} symbols")
    market_caps = _get_market_caps()
    sources = {"warn": {}, "osha": {}, "epa": {}, "fcc": {}, "lobby": {}}
    fetchers = [("warn", lambda: _fetch_warn_scores(universe, market_caps)), ("osha", lambda: _fetch_osha_scores(universe)),
                ("epa", lambda: _fetch_epa_scores(universe)), ("fcc", lambda: _fetch_fcc_scores(universe)),
                ("lobby", lambda: _fetch_lobbying_scores(universe))]
    for key, fn in fetchers:
        try: sources[key] = fn()
        except Exception as exc: print(f"    {key.upper()} source failed: {exc}"); traceback.print_exc()
    print("\n  Computing composite gov_intel_score ...")
    today_str = date.today().isoformat()
    score_rows, scored, non_neutral = [], 0, 0
    for sym in universe:
        s = {k: sources[k].get(sym, NEUTRAL_SCORE) for k in WEIGHTS}
        composite = round(sum(s[k] * WEIGHTS[k] for k in WEIGHTS), 1)
        if any(v != NEUTRAL_SCORE for v in s.values()): non_neutral += 1
        details = json.dumps({k: round(v, 1) for k, v in s.items()})
        score_rows.append((sym, today_str, composite, round(s["warn"], 1), round(s["osha"], 1),
            round(s["epa"], 1), round(s["fcc"], 1), round(s["lobby"], 1), details))
        scored += 1
    upsert_many("gov_intel_scores", ["symbol", "date", "gov_intel_score", "warn_score", "osha_score",
        "epa_score", "fcc_score", "lobbying_score", "details"], score_rows)
    print(f"  Stored {scored} scores ({non_neutral} with non-neutral data)\n" + "=" * 60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
