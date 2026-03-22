"""Digital Exhaust — app rankings, GitHub velocity, pricing & domain signals.
Produces 0-100 digital_exhaust_score per symbol. Weekly gate (7-day)."""
import json, logging, os, time
from datetime import date, datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tools.db import init_db, get_conn, query, upsert_many
from tools.config import SERPER_API_KEY

logger = logging.getLogger(__name__)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


def _make_session() -> requests.Session:
    """HTTP session with automatic retries on transient failures."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

APP_DEVELOPER_MAP = {
    "Meta Platforms, Inc.": "META", "Google LLC": "GOOGL", "Apple": "AAPL",
    "Amazon.com, Inc.": "AMZN", "Microsoft Corporation": "MSFT", "Snap, Inc.": "SNAP",
    "Pinterest, Inc.": "PINS", "Uber Technologies, Inc.": "UBER", "Block, Inc.": "SQ",
    "PayPal, Inc.": "PYPL", "Spotify AB": "SPOT", "Netflix, Inc.": "NFLX",
    "The Walt Disney Company": "DIS", "Paramount Global": "PARA",
    "Warner Bros. Discovery": "WBD", "Roblox Corporation": "RBLX",
    "DoorDash, Inc.": "DASH", "Airbnb, Inc.": "ABNB", "Booking.com": "BKNG",
    "Match Group, LLC": "MTCH", "Duolingo": "DUOL", "Peloton Interactive": "PTON",
    "Coinbase, Inc.": "COIN", "Robinhood Markets": "HOOD", "Instacart": "CART",
}
GITHUB_ORG_MAP = {
    "META": "facebook", "GOOGL": "google", "MSFT": "microsoft", "AMZN": "aws",
    "AAPL": "apple", "NVDA": "NVIDIA", "CRM": "salesforce", "ORCL": "oracle",
    "IBM": "IBM", "UBER": "uber", "ABNB": "airbnb", "SNAP": "Snapchat",
    "SQ": "square", "SHOP": "Shopify", "TWLO": "twilio", "NET": "cloudflare",
    "DDOG": "DataDog", "CRWD": "CrowdStrike", "PLTR": "palantir",
    "SNOW": "snowflakedb", "NOW": "ServiceNow", "WDAY": "Workday",
    "ZS": "zscaler", "PANW": "PaloAltoNetworks", "COIN": "coinbase",
}
SAAS_PRICING_TICKERS = ["CRM","NOW","SNOW","DDOG","NET","CRWD","ZS","PANW","WDAY","SHOP","TWLO","MSFT","GOOGL","AMZN"]
COMPANY_DOMAINS = {
    "META": "meta.com", "GOOGL": "google.com", "MSFT": "microsoft.com", "AMZN": "amazon.com",
    "AAPL": "apple.com", "NFLX": "netflix.com", "UBER": "uber.com", "ABNB": "airbnb.com",
    "CRM": "salesforce.com", "SHOP": "shopify.com", "SNAP": "snapchat.com",
    "SQ": "squareup.com", "COIN": "coinbase.com", "SPOT": "spotify.com", "DASH": "doordash.com",
}
ALL_COVERED_TICKERS = sorted(set(APP_DEVELOPER_MAP.values()) | set(GITHUB_ORG_MAP.keys()))

def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS digital_exhaust_raw (
            symbol TEXT, date TEXT, source TEXT, metric TEXT, value REAL,
            prior_value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric));
        CREATE TABLE IF NOT EXISTS digital_exhaust_scores (
            symbol TEXT, date TEXT, digital_exhaust_score REAL, app_score REAL,
            github_score REAL, pricing_score REAL, domain_score REAL, details TEXT,
            PRIMARY KEY (symbol, date));""")
    conn.commit(); conn.close()

def _should_run():
    rows = query("SELECT MAX(date) as last_date FROM digital_exhaust_scores")
    if not rows or rows[0]["last_date"] is None: return True
    return (date.today() - datetime.strptime(rows[0]["last_date"], "%Y-%m-%d").date()).days >= 7

def _rank_to_score(rank):
    if rank <= 10: return 95.0
    if rank <= 25: return 85.0
    if rank <= 50: return 75.0
    if rank <= 100: return 65.0
    if rank <= 200: return 55.0
    return 45.0

def _fetch_app_rankings(session: requests.Session):
    logger.info("[1/4] App Store rankings ...")
    scores = {}; best = {}
    for name, url in [("top-free", "https://rss.applemarketingtools.com/api/v2/us/apps/top-free/200/apps.json"),
                      ("top-grossing", "https://rss.applemarketingtools.com/api/v2/us/apps/top-grossing/200/apps.json")]:
        try:
            resp = session.get(url, timeout=15); resp.raise_for_status()
            for idx, app in enumerate(resp.json().get("feed",{}).get("results",[]), 1):
                t = APP_DEVELOPER_MAP.get(app.get("artistName",""))
                if t and (t not in best or idx < best[t]): best[t] = idx
        except Exception as e:
            logger.warning("App Store fetch failed for %s: %s", name, e)
        time.sleep(0.5)
    scores = {t: _rank_to_score(r) for t, r in best.items()}
    logger.info("  Found %d tickers in charts", len(scores))
    return scores

def _fetch_github_velocity(session: requests.Session):
    logger.info("[2/4] GitHub commit velocity ...")
    scores = {}
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN: headers["Authorization"] = f"token {GITHUB_TOKEN}"
    for ticker, org in GITHUB_ORG_MAP.items():
        try:
            resp = session.get(f"https://api.github.com/orgs/{org}/repos?sort=pushed&per_page=5",
                               headers=headers, timeout=15)
            if resp.status_code in (403, 429):
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning("GitHub rate-limited — sleeping %ds", wait)
                time.sleep(wait)
                scores[ticker] = 50.0; continue
            if resp.status_code != 200 or not resp.json(): scores[ticker] = 50.0; continue
            time.sleep(0.5)
            top = resp.json()[0].get("name","")
            r2 = session.get(f"https://api.github.com/repos/{org}/{top}/stats/commit_activity",
                             headers=headers, timeout=15)
            if r2.status_code != 200: scores[ticker] = 50.0; continue
            weeks = r2.json()
            if not isinstance(weeks, list) or len(weeks) < 4: scores[ticker] = 50.0; time.sleep(0.5); continue
            recent = sum(w.get("total",0) for w in weeks[-4:])
            prior = sum(w.get("total",0) for w in weeks[-8:-4])
            v = (recent / prior) if prior else (1.0 if recent > 0 else 0.0)
            if v >= 1.3: s = min(85.0, 65.0 + (v-1.3)*40)
            elif v >= 1.0: s = 55.0 + (v-1.0)/0.3*10
            elif v >= 0.7: s = 35.0 + (v-0.7)/0.3*20
            else: s = max(15.0, 35.0 - (0.7-v)*40)
            scores[ticker] = round(s, 1); time.sleep(0.5)
        except Exception as e:
            logger.debug("GitHub error for %s/%s: %s", ticker, org, e); scores[ticker] = 50.0
    logger.info("  Scored %d orgs", len(scores))
    return scores

def _fetch_pricing_signals(session: requests.Session):
    logger.info("[3/4] Pricing page signals ...")
    scores = {}
    if not SERPER_API_KEY:
        logger.warning("SERPER_API_KEY not set — pricing signals will default to 50")
        return {t: 50.0 for t in SAAS_PRICING_TICKERS}
    hdrs = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    for ticker in SAAS_PRICING_TICKERS:
        try:
            resp = session.post("https://google.serper.dev/search", headers=hdrs,
                json={"q": f"{ticker} stock pricing increase OR price hike OR raises prices", "num": 5, "tbs": "qdr:m"}, timeout=10)
            if resp.status_code != 200: scores[ticker] = 50.0; continue
            inc = dec = 0
            for r in resp.json().get("organic", []):
                sn = (r.get("snippet","") + r.get("title","")).lower()
                inc += any(k in sn for k in ["price increase","raises price","price hike","higher pricing"])
                dec += any(k in sn for k in ["price cut","lowers price","price decrease","cheaper"])
            scores[ticker] = 80.0 if inc >= 2 else 65.0 if inc == 1 else 25.0 if dec >= 2 else 40.0 if dec == 1 else 50.0
            time.sleep(0.5)
        except Exception as e:
            logger.debug("Pricing error for %s: %s", ticker, e); scores[ticker] = 50.0
    logger.info("  Scored %d SaaS tickers", len(scores))
    return scores

def _fetch_domain_signals(session: requests.Session):
    logger.info("[4/4] Domain / expansion signals ...")
    scores = {}
    for ticker, domain in COMPANY_DOMAINS.items():
        try:
            resp = session.get(f"https://rdap.verisign.com/com/v1/domain/{domain}", timeout=10)
            if resp.status_code != 200: scores[ticker] = 50.0; continue
            last_changed = None
            for ev in resp.json().get("events", []):
                if ev.get("eventAction") == "last changed": last_changed = ev.get("eventDate",""); break
            if last_changed:
                try:
                    days = (date.today() - datetime.fromisoformat(last_changed.replace("Z","+00:00")).date()).days
                    scores[ticker] = 75.0 if days <= 30 else 60.0 if days <= 90 else 50.0
                except (ValueError, TypeError): scores[ticker] = 50.0
            else: scores[ticker] = 50.0
            time.sleep(0.5)
        except Exception as e:
            logger.debug("RDAP error for %s: %s", ticker, e); scores[ticker] = 50.0
    logger.info("  Scored %d domains", len(scores))
    return scores

def _aggregate_scores(app, github, pricing, domain):
    today = date.today().isoformat(); rows = []
    all_t = set(app) | set(github) | set(pricing) | set(domain)
    for t in sorted(all_t):
        a, g, p, d = app.get(t,50.0), github.get(t,50.0), pricing.get(t,50.0), domain.get(t,50.0)
        c = round(a*0.30 + g*0.25 + p*0.25 + d*0.20, 1)
        rows.append((t, today, c, a, g, p, d,
                      json.dumps({"app_score":a,"github_score":g,"pricing_score":p,"domain_score":d})))
    covered = {r[0] for r in rows}
    for row in query("SELECT symbol FROM stock_universe"):
        if row["symbol"] not in covered:
            rows.append((row["symbol"], today, 50.0, 50.0, 50.0, 50.0, 50.0,
                         json.dumps({"note": "no digital exhaust data"})))
    return rows

def _store_raw(app, github, pricing, domain):
    today = date.today().isoformat(); raw = []
    for label, d in [("app_store",app),("github",github),("pricing",pricing),("domain",domain)]:
        for t, v in d.items():
            prior = query("SELECT value FROM digital_exhaust_raw WHERE symbol=? AND source=? AND metric='score' ORDER BY date DESC LIMIT 1", [t, label])
            raw.append((t, today, label, "score", v, prior[0]["value"] if prior else None, None))
    upsert_many("digital_exhaust_raw", ["symbol","date","source","metric","value","prior_value","details"], raw)

def run():
    init_db(); _ensure_tables()
    logger.info("=" * 60)
    logger.info("DIGITAL EXHAUST INTELLIGENCE")
    logger.info("=" * 60)
    if not _should_run():
        logger.info("Skipping — last run < 7 days ago")
        return
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set — GitHub velocity scores will default to 50")
    logger.info("Coverage: %d tickers (app/GitHub/pricing/domain maps)", len(ALL_COVERED_TICKERS))
    session = _make_session()
    try:
        app = _fetch_app_rankings(session)
        gh = _fetch_github_velocity(session)
        pricing = _fetch_pricing_signals(session)
        dom = _fetch_domain_signals(session)
    finally:
        session.close()
    _store_raw(app, gh, pricing, dom)
    rows = _aggregate_scores(app, gh, pricing, dom)
    logger.info("Scoring %d symbols ...", len(rows))
    upsert_many("digital_exhaust_scores",
        ["symbol","date","digital_exhaust_score","app_score","github_score","pricing_score","domain_score","details"], rows)
    logger.info("Stored %d digital exhaust scores", len(rows))
    logger.info("=" * 60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
