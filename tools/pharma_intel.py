"""Pharma Intelligence — clinical trials, CMS utilization, Rx trends. Weekly, healthcare sector only."""
import json, logging, time
from datetime import date, datetime, timedelta
import requests
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)
PHARMA_SPONSOR_MAP = {
    "Pfizer": "PFE", "Eli Lilly": "LLY", "Eli Lilly and Company": "LLY", "Johnson & Johnson": "JNJ",
    "Merck Sharp & Dohme": "MRK", "Merck": "MRK", "AbbVie": "ABBV", "Bristol-Myers Squibb": "BMY",
    "Bristol Myers Squibb": "BMY", "Amgen": "AMGN", "Gilead Sciences": "GILD",
    "Regeneron Pharmaceuticals": "REGN", "Vertex Pharmaceuticals": "VRTX", "Moderna": "MRNA",
    "Biogen": "BIIB", "Illumina": "ILMN", "AstraZeneca": "AZN", "Novartis": "NVS", "Roche": "RHHBY",
    "Novo Nordisk": "NVO", "Sanofi": "SNY", "GSK": "GSK", "Takeda": "TAK", "Daiichi Sankyo": "DSNKY",
    "BioNTech": "BNTX", "Argenx": "ARGX", "Alnylam Pharmaceuticals": "ALNY", "Exact Sciences": "EXAS",
    "Intuitive Surgical": "ISRG", "Edwards Lifesciences": "EW", "Stryker": "SYK", "Medtronic": "MDT",
    "Abbott Laboratories": "ABT", "Becton Dickinson": "BDX", "Boston Scientific": "BSX",
    "Dexcom": "DXCM", "Hologic": "HOLX", "UnitedHealth Group": "UNH", "Elevance Health": "ELV",
    "Cigna": "CI", "Humana": "HUM", "Centene": "CNC", "HCA Healthcare": "HCA", "Tenet Healthcare": "THC",
    "CVS Health": "CVS", "Walgreens": "WBA", "McKesson": "MCK", "Cardinal Health": "CAH",
}
TICKER_TO_SPONSORS: dict[str, list[str]] = {}
for _s, _t in PHARMA_SPONSOR_MAP.items(): TICKER_TO_SPONSORS.setdefault(_t, []).append(_s)
PHASE_ORDER = {"EARLY_PHASE1": 0, "PHASE1": 1, "PHASE2": 2, "PHASE3": 3, "PHASE4": 4}
CT_BASE = "https://clinicaltrials.gov/api/v2/studies"
UTILIZATION_PROXIES = {"UNH": "managed_care", "ELV": "managed_care", "CI": "managed_care", "HUM": "managed_care",
    "CNC": "managed_care", "HCA": "hospital", "THC": "hospital", "MCK": "distributor", "CAH": "distributor",
    "CVS": "pharmacy", "WBA": "pharmacy", "MDT": "device", "ABT": "device", "BSX": "device", "SYK": "device",
    "EW": "device", "ISRG": "device", "BDX": "device", "DXCM": "device", "HOLX": "device"}
RX_HEAVY_TICKERS = {"PFE","LLY","MRK","ABBV","BMY","AMGN","GILD","REGN","VRTX","MRNA","BIIB","AZN","NVS","NVO","SNY","GSK","TAK","BNTX","ALNY","ARGX"}

def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pharma_intel_raw (symbol TEXT, date TEXT, source TEXT, metric TEXT, value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric));
        CREATE TABLE IF NOT EXISTS pharma_intel_scores (symbol TEXT, date TEXT, pharma_intel_score REAL, trial_velocity_score REAL, stage_shift_score REAL, cms_score REAL, rx_score REAL, details TEXT, PRIMARY KEY (symbol, date));
    """)
    conn.commit(); conn.close()

def _should_run():
    rows = query("SELECT MAX(date) as last_run FROM pharma_intel_scores")
    if not rows or not rows[0]["last_run"]: return True
    return (date.today() - datetime.strptime(rows[0]["last_run"], "%Y-%m-%d").date()).days >= 7

def _get_healthcare_symbols(): return [r["symbol"] for r in query("SELECT symbol FROM stock_universe WHERE sector = 'Health Care'")]

def _parse_phase(phase_list):
    if not phase_list: return None
    if isinstance(phase_list, str): phase_list = [phase_list]
    best, best_order = None, -1
    for p in phase_list:
        clean = p.upper().replace(" ", "").replace("/", "")
        for key, order in PHASE_ORDER.items():
            if key in clean and order > best_order: best, best_order = key, order
    return best

def _score_trials(studies):
    today = date.today(); cutoff_90d = today - timedelta(days=90)
    total_active, new_90d, phase_counts, advanced, enroll_ratios = len(studies), 0, {}, 0, []
    for study in studies:
        proto = study.get("protocolSection", {}); status_mod = proto.get("statusModule", {}); design_mod = proto.get("designModule", {})
        start_str = status_mod.get("startDateStruct", {}).get("date", "")
        if start_str:
            try:
                if len(start_str) == 7: start_str += "-01"
                if datetime.strptime(start_str, "%Y-%m-%d").date() >= cutoff_90d: new_90d += 1
            except ValueError: pass
        phase = _parse_phase(design_mod.get("phases", []))
        if phase:
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            if phase in ("PHASE3", "PHASE4"): advanced += 1
        enroll_info = design_mod.get("enrollmentInfo", {})
        if enroll_info.get("count"):
            enroll_ratios.append(1.0 if (enroll_info.get("type","")).upper() == "ACTUAL" else 0.5)
    if total_active == 0: return {"total_active": 0, "new_90d": 0, "phase_counts": {}, "advanced_phases": 0, "enrollment_ratio": None, "trial_velocity_score": 30.0, "stage_shift_score": 30.0}
    base = min(total_active / 30.0 * 40.0, 40.0); new_bonus = min(new_90d / 8.0 * 25.0, 25.0)
    adv_bonus = min(advanced / 10.0 * 25.0, 25.0); avg_enroll = sum(enroll_ratios) / len(enroll_ratios) if enroll_ratios else 0.5
    tvs = min(base + new_bonus + adv_bonus + avg_enroll * 10.0, 100.0)
    p3r = advanced / max(total_active, 1); p2r = phase_counts.get("PHASE2", 0) / max(total_active, 1)
    sss = min(p3r * 60.0 + p2r * 30.0 + 20.0, 100.0)
    return {"total_active": total_active, "new_90d": new_90d, "phase_counts": phase_counts, "advanced_phases": advanced,
        "enrollment_ratio": sum(enroll_ratios) / len(enroll_ratios) if enroll_ratios else None,
        "trial_velocity_score": round(tvs, 1), "stage_shift_score": round(sss, 1)}

def _fetch_clinical_trials(healthcare_symbols):
    results, processed = {}, set()
    for sponsor, ticker in PHARMA_SPONSOR_MAP.items():
        if ticker in processed or ticker not in healthcare_symbols: continue
        all_studies = []
        for sp in TICKER_TO_SPONSORS.get(ticker, [sponsor]):
            print(f"  [CT.gov] {sp} ({ticker})...")
            try:
                resp = requests.get(CT_BASE, params={"query.spons": sp, "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION", "pageSize": 50}, timeout=30)
                resp.raise_for_status(); all_studies.extend(resp.json().get("studies", []))
            except Exception as e: logger.warning(f"ClinicalTrials.gov error for {sp}: {e}")
            time.sleep(0.5)
        seen_ncts, unique = set(), []
        for s in all_studies:
            nct = s.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "")
            if nct and nct not in seen_ncts: seen_ncts.add(nct); unique.append(s)
            elif not nct: unique.append(s)
        results[ticker] = _score_trials(unique); processed.add(ticker)
    return results

def _compute_cms_scores(healthcare_symbols):
    scores, lookback = {}, (date.today() - timedelta(days=120)).isoformat()
    proxy_returns = {"managed_care": [], "hospital": [], "distributor": [], "pharmacy": [], "device": []}
    for symbol, category in UTILIZATION_PROXIES.items():
        rows = query("SELECT close FROM price_data WHERE symbol = ? AND date >= ? ORDER BY date ASC", [symbol, lookback])
        if len(rows) >= 2: proxy_returns[category].append((rows[-1]["close"] - rows[0]["close"]) / rows[0]["close"])
    cat_scores = {cat: max(10, min(90, 50 + (sum(r)/len(r)) * 150)) if r else 50.0 for cat, r in proxy_returns.items()}
    overall = sum(cat_scores.values()) / len(cat_scores) if cat_scores else 50.0
    for sym in healthcare_symbols:
        if sym in UTILIZATION_PROXIES: scores[sym] = round(cat_scores.get(UTILIZATION_PROXIES[sym], 50.0) * 0.7 + overall * 0.3, 1)
        else: scores[sym] = round(overall, 1)
    return scores

def _compute_rx_scores(healthcare_symbols):
    scores, lookback = {}, (date.today() - timedelta(days=60)).isoformat()
    sector_returns, symbol_returns = [], {}
    for sym in healthcare_symbols:
        rows = query("SELECT close FROM price_data WHERE symbol = ? AND date >= ? ORDER BY date ASC", [sym, lookback])
        if len(rows) >= 2:
            ret = (rows[-1]["close"] - rows[0]["close"]) / rows[0]["close"]
            symbol_returns[sym] = ret; sector_returns.append(ret)
    sector_avg = sum(sector_returns) / len(sector_returns) if sector_returns else 0.0
    for sym in healthcare_symbols:
        if sym in symbol_returns:
            rel = symbol_returns[sym] - sector_avg
            base = (55 + rel * 300) if sym in RX_HEAVY_TICKERS else (50 + rel * 150)
            scores[sym] = round(max(10, min(90, base)), 1)
        else: scores[sym] = 50.0
    return scores

def run():
    print("=" * 60 + "\nPHARMA INTELLIGENCE MODULE\n" + "=" * 60)
    init_db(); _ensure_tables()
    if not _should_run(): print("  Skipping — last run < 7 days ago."); return
    hc = _get_healthcare_symbols()
    if not hc: print("  No healthcare symbols."); return
    print(f"  {len(hc)} healthcare symbols.")
    try: trial_data = _fetch_clinical_trials(hc); print(f"  Trial data for {len(trial_data)} tickers.")
    except Exception as e: logger.error(f"Clinical trials failed: {e}"); trial_data = {}
    try: cms_scores = _compute_cms_scores(hc)
    except Exception: cms_scores = {}
    try: rx_scores = _compute_rx_scores(hc)
    except Exception: rx_scores = {}
    today = date.today().isoformat(); raw_rows = []
    for sym, td in trial_data.items():
        for metric in ["total_active", "new_90d", "advanced_phases", "trial_velocity_score", "stage_shift_score"]:
            raw_rows.append((sym, today, "clinicaltrials", metric, td[metric], json.dumps(td["phase_counts"]) if metric == "total_active" else None))
    for sym, s in cms_scores.items(): raw_rows.append((sym, today, "cms_proxy", "utilization_score", s, None))
    for sym, s in rx_scores.items(): raw_rows.append((sym, today, "rx_proxy", "rx_trend_score", s, None))
    if raw_rows: upsert_many("pharma_intel_raw", ["symbol", "date", "source", "metric", "value", "details"], raw_rows)
    score_rows = []
    for sym in hc:
        td = trial_data.get(sym)
        trial_score = (td["trial_velocity_score"] * 0.6 + td["stage_shift_score"] * 0.4) if td else 50.0
        stage_shift = td["stage_shift_score"] if td else 50.0
        cms, rx = cms_scores.get(sym, 50.0), rx_scores.get(sym, 50.0)
        pharma_score = max(0, min(100, round(trial_score * 0.45 + cms * 0.25 + rx * 0.30, 1)))
        details = json.dumps({"trial_velocity": round(trial_score, 1), "stage_shift": round(stage_shift, 1),
            "cms": cms, "rx": rx, "has_trial_data": td is not None,
            "active_trials": td["total_active"] if td else 0, "advanced_phases": td["advanced_phases"] if td else 0})
        score_rows.append((sym, today, pharma_score, round(trial_score, 1), round(stage_shift, 1), cms, rx, details))
    upsert_many("pharma_intel_scores", ["symbol","date","pharma_intel_score","trial_velocity_score","stage_shift_score","cms_score","rx_score","details"], score_rows)
    if score_rows:
        avg_s = sum(r[2] for r in score_rows) / len(score_rows)
        print(f"\n  Scored {len(score_rows)} symbols. Avg: {avg_s:.1f}")
        for r in sorted(score_rows, key=lambda r: r[2], reverse=True)[:5]:
            print(f"    {r[0]:6s}  score={r[2]:.1f}  (trial={r[3]:.0f}  cms={r[5]:.0f}  rx={r[6]:.0f})")
    print("=" * 60 + "\nPHARMA INTELLIGENCE COMPLETE\n" + "=" * 60)

if __name__ == "__main__": run()
