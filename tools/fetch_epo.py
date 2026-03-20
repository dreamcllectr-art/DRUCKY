"""European Patent Office (EPO) patent intelligence fetcher.

Supplements patent_intel.py (USPTO) with European patent data.
Table: epo_patents
"""
import logging
import time
import requests
import base64
from datetime import date, timedelta
from tools.db import get_conn, query, upsert_many
from tools.config import EPO_CONSUMER_KEY, EPO_CONSUMER_SECRET

logger = logging.getLogger(__name__)

EPO_AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"
EPO_SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search"
EPO_REFRESH_DAYS = 7


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS epo_patents (
    company_name TEXT, symbol TEXT, date TEXT,
    filing_count INTEGER, grant_count INTEGER, tech_class TEXT,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _get_access_token():
    credentials = f"{EPO_CONSUMER_KEY}:{EPO_CONSUMER_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        r = requests.post(EPO_AUTH_URL,
                          data={"grant_type": "client_credentials"},
                          headers=headers, timeout=15)
        r.raise_for_status()
        return r.json().get("access_token")
    except Exception as e:
        logger.warning(f"EPO auth failed: {e}")
        return None


def _search_patents(token, company_name, since_date):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    # CQL query for company filings in last 12 months
    query_str = f'pa="{company_name}" AND pd>={since_date}'
    try:
        r = requests.get(EPO_SEARCH_URL,
                         params={"q": query_str, "Range": "1-25"},
                         headers=headers, timeout=20)
        if r.status_code == 404:
            return 0
        r.raise_for_status()
        data = r.json()
        # Extract total count from response
        results = data.get("ops:world-patent-data", {}).get(
            "ops:biblio-search", {}
        )
        total = results.get("@total-result-count", "0")
        return int(total) if str(total).isdigit() else 0
    except Exception as e:
        logger.debug(f"EPO search for {company_name}: {e}")
        return 0


def _needs_refresh():
    recent = query(
        "SELECT COUNT(*) as cnt FROM epo_patents WHERE date >= date('now', ? || ' days')",
        [f"-{EPO_REFRESH_DAYS}"]
    )
    return not recent or recent[0]["cnt"] < 10


def run():
    if not EPO_CONSUMER_KEY or not EPO_CONSUMER_SECRET:
        print("  EPO API keys not set — skipping")
        return

    _ensure_tables()

    if not _needs_refresh():
        print("  EPO patents: recently fetched, skipping")
        return

    token = _get_access_token()
    if not token:
        print("  EPO auth failed — skipping")
        return

    # Focus on high-value patent-intensive companies
    symbols = [r["symbol"] for r in query(
        """SELECT DISTINCT u.symbol FROM stock_universe u
           JOIN fundamentals f ON u.symbol = f.symbol
           WHERE f.metric = 'sector' AND f.value IN (0, 1)
           LIMIT 100"""
    )]
    if not symbols:
        # Fallback: tech companies by name pattern
        symbols = [r["symbol"] for r in query(
            """SELECT symbol FROM stock_universe
               WHERE sector IN ('Technology', 'Health Care', 'Industrials')
               LIMIT 100"""
        )]

    since_date = (date.today() - timedelta(days=365)).strftime("%Y%m%d")
    today = date.today().isoformat()
    rows = []
    names = {r["symbol"]: r["name"] for r in query("SELECT symbol, name FROM stock_universe")}

    print(f"  Fetching EPO patents for {len(symbols)} companies...")
    for sym in symbols[:50]:  # Limit per run
        company = names.get(sym, sym)
        count = _search_patents(token, company, since_date)
        if count > 0:
            rows.append((company, sym, today, count, 0, ""))
        time.sleep(0.5)

    if rows:
        upsert_many("epo_patents",
                    ["company_name", "symbol", "date", "filing_count", "grant_count", "tech_class"],
                    rows)
    print(f"  EPO: {len(rows)} companies with patent data")
