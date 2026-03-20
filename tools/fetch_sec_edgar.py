"""SEC EDGAR direct fetcher.

No API key. Rate limit: 10 req/sec.
Data: Form 4 insider transactions (supplement), 13F metadata
Tables: edgar_insider_raw, edgar_filing_metadata
"""
import logging
import time
import requests
from datetime import date, timedelta
from tools.db import get_conn, query, upsert_many
from tools.config import EDGAR_HEADERS

logger = logging.getLogger(__name__)

EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_DATA = "https://data.sec.gov"
REQUEST_DELAY = 0.12  # Stay under 10 req/sec


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS edgar_insider_raw (
    accession TEXT PRIMARY KEY,
    symbol TEXT, date TEXT, filer_name TEXT, title TEXT,
    transaction_type TEXT, shares REAL, price REAL, value REAL,
    form_type TEXT, filing_url TEXT
);
CREATE TABLE IF NOT EXISTS edgar_filing_metadata (
    accession TEXT PRIMARY KEY,
    symbol TEXT, date TEXT, form_type TEXT,
    filer_name TEXT, filing_url TEXT, description TEXT
);
    """)
    conn.commit()
    conn.close()


def _get(url, params=None):
    try:
        r = requests.get(url, params=params, headers=EDGAR_HEADERS, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"EDGAR request failed {url}: {e}")
        return None


def _fetch_form4_recent(days_back=2):
    """Fetch recent Form 4 filings (insider transactions)."""
    since = (date.today() - timedelta(days=days_back)).isoformat()
    params = {
        "q": "form-type:4",
        "dateRange": "custom",
        "startdt": since,
        "enddt": date.today().isoformat(),
        "_source": "file-index-hits",
        "hits.hits.total.value": True,
        "hits.hits._source.period_of_report": True,
    }
    # Use full-text search endpoint
    url = "https://efts.sec.gov/LATEST/search-index?q=%22form-type%3A4%22&dateRange=custom"
    data = _get(
        "https://efts.sec.gov/LATEST/search-index",
        {"q": '"4"', "dateRange": "custom",
         "startdt": since, "enddt": date.today().isoformat(),
         "forms": "4", "_source": "period_of_report,file_date,entity_name,ticker_symbol"}
    )
    return data


def _fetch_recent_form4_edgar():
    """Fetch Form 4 filings from EDGAR full-text search."""
    since = (date.today() - timedelta(days=3)).isoformat()
    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "forms": "4",
        "dateRange": "custom",
        "startdt": since,
        "enddt": date.today().isoformat(),
    }
    try:
        r = requests.get(url, params=params, headers=EDGAR_HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits", {}).get("hits", [])
        return hits
    except Exception as e:
        logger.debug(f"EDGAR Form4 search failed: {e}")
        return []


def run():
    _ensure_tables()
    print("  Fetching SEC EDGAR Form 4 filings...")

    hits = _fetch_recent_form4_edgar()
    rows = []
    meta_rows = []
    today = date.today().isoformat()

    for hit in hits[:200]:  # Limit to 200 per run
        src = hit.get("_source", {})
        accession = hit.get("_id", "")
        ticker = src.get("ticker_symbol", "")
        entity = src.get("entity_name", "")
        file_date = src.get("file_date", today)
        filing_url = f"https://www.sec.gov/Archives/edgar/{accession.replace('-', '/')}.txt" if accession else ""

        if ticker:
            meta_rows.append((
                accession, ticker, file_date, "4",
                entity, filing_url, "Insider transaction Form 4"
            ))
        time.sleep(REQUEST_DELAY)

    if meta_rows:
        upsert_many("edgar_filing_metadata",
                    ["accession", "symbol", "date", "form_type",
                     "filer_name", "filing_url", "description"],
                    meta_rows)

    print(f"  EDGAR: {len(meta_rows)} Form 4 filings metadata stored")
