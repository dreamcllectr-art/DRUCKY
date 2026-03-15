"""Labor Market Intelligence — H-1B velocity, job postings, employee sentiment.
Produces 0-100 labor_intel_score per symbol. Weekly gate (7-day)."""
import json, logging, re, time
from datetime import date, datetime
import requests
from tools.db import init_db, get_conn, query, upsert_many
from tools.config import SERPER_API_KEY

logger = logging.getLogger(__name__)
WEIGHTS = {"h1b": 0.40, "hiring": 0.35, "sentiment": 0.25}
NEUTRAL = 50
RATE_LIMIT_SEC = 0.5

H1B_EMPLOYER_MAP = {
    "GOOGLE LLC": "GOOGL", "ALPHABET INC": "GOOGL", "APPLE INC": "AAPL",
    "MICROSOFT CORPORATION": "MSFT", "META PLATFORMS": "META",
    "AMAZON.COM SERVICES LLC": "AMZN", "NVIDIA CORPORATION": "NVDA", "TESLA INC": "TSLA",
    "SALESFORCE INC": "CRM", "ORACLE AMERICA INC": "ORCL", "INTEL CORPORATION": "INTC",
    "QUALCOMM INC": "QCOM", "CISCO SYSTEMS": "CSCO", "ADOBE INC": "ADBE",
    "IBM": "IBM", "PAYPAL INC": "PYPL", "UBER TECHNOLOGIES": "UBER",
    "AIRBNB INC": "ABNB", "SNAP INC": "SNAP", "PINTEREST INC": "PINS",
    "BROADCOM INC": "AVGO", "ADVANCED MICRO DEVICES": "AMD",
    "SERVICENOW INC": "NOW", "WORKDAY INC": "WDAY", "PALANTIR TECHNOLOGIES": "PLTR",
    "DATADOG INC": "DDOG", "CROWDSTRIKE": "CRWD", "SNOWFLAKE INC": "SNOW",
    "JPMORGAN CHASE": "JPM", "GOLDMAN SACHS": "GS", "MORGAN STANLEY": "MS",
    "BANK OF AMERICA": "BAC", "WELLS FARGO": "WFC", "CITIGROUP": "C",
    "UNITEDHEALTH GROUP": "UNH", "JOHNSON & JOHNSON": "JNJ", "PFIZER INC": "PFE",
    "ELI LILLY": "LLY", "MERCK & CO": "MRK", "ABBVIE INC": "ABBV",
    "DELOITTE": None, "ACCENTURE": "ACN", "COGNIZANT TECHNOLOGY": "CTSH",
    "INFOSYS": "INFY", "TATA CONSULTANCY": None, "WIPRO": "WIT",
    "HCL AMERICA": None, "CAPGEMINI": None,
}
TICKER_TO_EMPLOYERS = {}
for _e, _t in H1B_EMPLOYER_MAP.items():
    if _t: TICKER_TO_EMPLOYERS.setdefault(_t, []).append(_e)

TICKER_TO_COMPANY = {
    "GOOGL":"Google","AAPL":"Apple","MSFT":"Microsoft","META":"Meta","AMZN":"Amazon",
    "NVDA":"Nvidia","TSLA":"Tesla","CRM":"Salesforce","ORCL":"Oracle","INTC":"Intel",
    "QCOM":"Qualcomm","CSCO":"Cisco","ADBE":"Adobe","IBM":"IBM","PYPL":"PayPal",
    "UBER":"Uber","ABNB":"Airbnb","SNAP":"Snap","PINS":"Pinterest","AVGO":"Broadcom",
    "AMD":"AMD","NOW":"ServiceNow","WDAY":"Workday","PLTR":"Palantir","DDOG":"Datadog",
    "CRWD":"CrowdStrike","SNOW":"Snowflake","JPM":"JPMorgan Chase","GS":"Goldman Sachs",
    "MS":"Morgan Stanley","BAC":"Bank of America","WFC":"Wells Fargo","C":"Citigroup",
    "UNH":"UnitedHealth Group","JNJ":"Johnson & Johnson","PFE":"Pfizer","LLY":"Eli Lilly",
    "MRK":"Merck","ABBV":"AbbVie","ACN":"Accenture","CTSH":"Cognizant","INFY":"Infosys",
    "WIT":"Wipro",
}

def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS labor_intel_raw (
            symbol TEXT, date TEXT, source TEXT, metric TEXT, value REAL,
            details TEXT, PRIMARY KEY (symbol, date, source, metric));
        CREATE TABLE IF NOT EXISTS labor_intel_scores (
            symbol TEXT, date TEXT, labor_intel_score REAL, h1b_score REAL,
            hiring_score REAL, morale_score REAL, details TEXT, PRIMARY KEY (symbol, date));""")
    conn.commit(); conn.close()

def _should_run():
    rows = query("SELECT MAX(date) as last_run FROM labor_intel_scores")
    if not rows or not rows[0]["last_run"]: return True
    return (date.today() - datetime.strptime(rows[0]["last_run"], "%Y-%m-%d").date()).days >= 7

def _serper_search(q, num=10):
    if not SERPER_API_KEY: return []
    try:
        resp = requests.post("https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": q, "num": num}, timeout=15)
        resp.raise_for_status(); return resp.json().get("organic", [])
    except Exception as e:
        logger.warning("Serper failed for '%s': %s", q, e); return []

def _keyword_score(results, pos_kw, neg_kw):
    pos = neg = 0
    for r in results:
        text = (r.get("snippet","") + " " + r.get("title","")).lower()
        pos += sum(1 for k in pos_kw if k in text)
        neg += sum(1 for k in neg_kw if k in text)
    return pos, neg

def _fetch_h1b_scores():
    scores = {}; today_str = date.today().isoformat()
    session = requests.Session()
    for ticker, employers in TICKER_TO_EMPLOYERS.items():
        total_recent = total_prior = 0
        for employer in employers:
            try:
                resp = session.get("https://api.dol.gov/V1/Statistics/LCA",
                    params={"$filter": f"EMPLOYER_NAME eq '{employer}'",
                            "$select": "EMPLOYER_NAME,CASE_NUMBER,CASE_STATUS,RECEIVED_DATE",
                            "$top": "100", "$orderby": "RECEIVED_DATE desc"}, timeout=15)
                time.sleep(RATE_LIMIT_SEC)
                if resp.status_code != 200: continue
                data = resp.json(); results = data.get("d", data.get("results", []))
                if isinstance(results, dict): results = results.get("results", [])
                now = date.today()
                for r in results:
                    rd = r.get("RECEIVED_DATE", "")
                    try:
                        if "/Date(" in str(rd):
                            filing_date = date.fromtimestamp(int(re.search(r"/Date\((\d+)\)", str(rd)).group(1)) / 1000)
                        else:
                            filing_date = datetime.strptime(str(rd)[:10], "%Y-%m-%d").date()
                        days = (now - filing_date).days
                        if days <= 90: total_recent += 1
                        elif days <= 180: total_prior += 1
                    except (ValueError, TypeError, AttributeError): total_recent += 1
            except Exception as e:
                logger.warning("H-1B fetch failed for %s: %s", employer, e)
        if total_recent == 0 and total_prior == 0:
            company = TICKER_TO_COMPANY.get(ticker, ticker)
            results = _serper_search(f'"{company}" H-1B visa hiring 2024 2025', num=5)
            time.sleep(RATE_LIMIT_SEC)
            pos, neg = _keyword_score(results,
                ["hiring","expansion","increase","growth","ramp","adding"],
                ["layoff","freeze","cutting","reduction","decline","halt"])
            score = min(80, 55+(pos-neg)*5) if pos > neg else max(20, 45-(neg-pos)*5) if neg > pos else NEUTRAL
        else:
            v = ((total_recent - total_prior) / total_prior) if total_prior else (1.0 if total_recent > 0 else 0.0)
            if v > 0.5: score = min(100, 80 + v*40)
            elif v > 0: score = 60 + v*40
            elif v > -0.2: score = 40 + (v+0.2)*100
            else: score = max(0, 40 + v*100)
            score = round(max(0, min(100, score)), 1)
        scores[ticker] = score
        upsert_many("labor_intel_raw", ["symbol","date","source","metric","value","details"],
            [(ticker, today_str, "h1b", "recent_filings", total_recent,
              json.dumps({"employers": employers, "prior_filings": total_prior}))])
    print(f"    H-1B scores: {len(scores)} tickers"); return scores

def _fetch_job_posting_scores():
    scores = {}; today_str = date.today().isoformat()
    for ticker, company in TICKER_TO_COMPANY.items():
        try:
            results = _serper_search(f'"{company}" hiring OR careers site:linkedin.com/jobs', num=10)
            time.sleep(RATE_LIMIT_SEC)
            if not results: scores[ticker] = NEUTRAL; continue
            rc = len(results)
            exp, con = _keyword_score(results,
                ["hiring","open positions","we're growing","join our team","multiple openings","urgently hiring"],
                ["layoff","restructuring","freeze","workforce reduction","downsizing"])
            base = 65 if rc >= 8 else 55 if rc >= 5 else 40 if rc <= 2 else 50
            scores[ticker] = round(max(0, min(100, base + (exp-con)*3)), 1)
            upsert_many("labor_intel_raw", ["symbol","date","source","metric","value","details"],
                [(ticker, today_str, "job_postings", "search_results", rc,
                  json.dumps({"expansion_hits": exp, "contraction_hits": con}))])
        except Exception as e:
            logger.warning("Job posting fetch failed for %s: %s", ticker, e); scores[ticker] = NEUTRAL
    print(f"    Job posting scores: {len(scores)} tickers"); return scores

def _extract_rating(results):
    if not results: return None
    pats = [r"(\d\.\d)\s*(?:out of|\/)\s*5", r"(?:rating|rated|stars?)[:\s]*(\d\.\d)",
            r"(\d\.\d)\s*stars?", r"★\s*(\d\.\d)", r"(\d\.\d)\s*overall"]
    for r in results:
        text = (r.get("snippet","") + " " + r.get("title","")).lower()
        for p in pats:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                v = float(m.group(1))
                if 1.0 <= v <= 5.0: return v
    return None

def _fetch_sentiment_scores():
    scores = {}; today_str = date.today().isoformat()
    for ticker, company in TICKER_TO_COMPANY.items():
        try:
            rating = _extract_rating(_serper_search(f'"{company}" glassdoor rating reviews', num=5))
            time.sleep(RATE_LIMIT_SEC)
            if rating is None:
                rating = _extract_rating(_serper_search(f'"{company}" indeed company reviews rating', num=5))
                time.sleep(RATE_LIMIT_SEC)
            if rating is not None:
                if rating >= 4.5: s = 90
                elif rating >= 4.0: s = 70 + (rating-4.0)*40
                elif rating >= 3.0: s = 40 + (rating-3.0)*30
                elif rating >= 2.0: s = 10 + (rating-2.0)*30
                else: s = 10
                s = round(max(0, min(100, s)), 1)
            else: s = NEUTRAL
            scores[ticker] = s
            upsert_many("labor_intel_raw", ["symbol","date","source","metric","value","details"],
                [(ticker, today_str, "sentiment", "glassdoor_rating", rating if rating else -1,
                  json.dumps({"source":"serper_glassdoor","rating_found": rating is not None}))])
        except Exception as e:
            logger.warning("Sentiment fetch failed for %s: %s", ticker, e); scores[ticker] = NEUTRAL
    print(f"    Sentiment scores: {len(scores)} tickers"); return scores

def run():
    init_db(); _ensure_tables()
    print("\n" + "="*60 + "\n  LABOR MARKET INTELLIGENCE\n" + "="*60)
    if not _should_run(): print("  Skipping -- last run < 7 days ago\n" + "="*60); return
    print("  [1/3] H-1B LCA filing velocity ..."); h1b = _fetch_h1b_scores()
    print("  [2/3] Job posting velocity ..."); jobs = _fetch_job_posting_scores()
    print("  [3/3] Employee sentiment ..."); sent = _fetch_sentiment_scores()
    today_str = date.today().isoformat()
    all_t = set(h1b) | set(jobs) | set(sent)
    rows = []
    for t in sorted(all_t):
        h, hi, mo = h1b.get(t,NEUTRAL), jobs.get(t,NEUTRAL), sent.get(t,NEUTRAL)
        sc = round(h*WEIGHTS["h1b"] + hi*WEIGHTS["hiring"] + mo*WEIGHTS["sentiment"], 1)
        rows.append((t, today_str, sc, h, hi, mo,
                      json.dumps({"h1b_score":h,"hiring_score":hi,"morale_score":mo,"weights":WEIGHTS})))
    upsert_many("labor_intel_scores",
        ["symbol","date","labor_intel_score","h1b_score","hiring_score","morale_score","details"], rows)
    if rows:
        avg = sum(r[2] for r in rows) / len(rows)
        top = sorted(rows, key=lambda r: r[2], reverse=True)[:5]
        bot = sorted(rows, key=lambda r: r[2])[:5]
        print(f"\n  Scored {len(rows)} symbols (avg: {avg:.1f})")
        for label, items in [("Top 5", top), ("Bottom 5", bot)]:
            print(f"\n  {label}:")
            for r in items: print(f"    {r[0]:<8} {r[2]:>5.1f}  (H1B={r[3]:.0f} Hiring={r[4]:.0f} Morale={r[5]:.0f})")
    print("\n" + "="*60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
