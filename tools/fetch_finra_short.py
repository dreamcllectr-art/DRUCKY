"""FINRA short interest fetcher — official semi-monthly data.

No API key. Public FINRA RegSHO data.
Table: finra_short_interest
Updates semi-monthly (15th and last business day of month).
"""
import logging
import time
import requests
from datetime import date
from tools.db import get_conn, query, upsert_many

logger = logging.getLogger(__name__)

FINRA_API = "https://api.finra.org/data/group/otcMarket/name/regShoDaily"
FINRA_SHORT_API = "https://api.finra.org/data/group/otcMarket/name/weeklySummary"
NASDAQ_SHORT_URL = "https://www.nasdaqtrader.com/dynamic/symdir/shortsales"


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS finra_short_interest (
    symbol TEXT, date TEXT,
    short_volume REAL, total_volume REAL, short_vol_ratio REAL,
    short_interest REAL, days_to_cover REAL,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _fetch_finra_regsho():
    """Fetch RegSHO short volume data from FINRA API."""
    today = date.today().isoformat()
    url = "https://api.finra.org/data/group/otcMarket/name/regShoDaily"
    params = {
        "limit": 5000,
        "offset": 0,
        "fields": "issueSymbolIdentifier,totalParValue,shortParValue,settlementDate",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"FINRA RegSHO failed: {e}")
        return []


def _fetch_nasdaq_short_interest():
    """Fetch NASDAQ short interest file (semi-monthly)."""
    # NASDAQ provides a flat file of current short interest
    # Check if we already have recent data
    recent = query(
        "SELECT COUNT(*) as cnt FROM finra_short_interest WHERE date >= date('now', '-15 days')"
    )
    if recent and recent[0]["cnt"] > 100:
        logger.debug("FINRA short interest recently fetched, skipping")
        return []

    url = "https://www.nasdaqtrader.com/dynamic/symdir/shortsales/nasdaqshortinterest.txt"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        lines = r.text.strip().split("\n")
        rows = []
        today = date.today().isoformat()
        for line in lines[1:]:  # Skip header
            parts = line.strip().split("|")
            if len(parts) >= 4:
                symbol = parts[0].strip()
                try:
                    short_interest = float(parts[1].replace(",", "")) if parts[1] else None
                    days_to_cover = float(parts[3]) if len(parts) > 3 and parts[3] else None
                    rows.append((symbol, today, None, None, None, short_interest, days_to_cover))
                except (ValueError, IndexError):
                    continue
        return rows
    except Exception as e:
        logger.debug(f"NASDAQ short interest failed: {e}")
        return []


def run():
    _ensure_tables()
    print("  Fetching FINRA/NASDAQ short interest data...")

    rows = _fetch_nasdaq_short_interest()

    if rows:
        upsert_many("finra_short_interest",
                    ["symbol", "date", "short_volume", "total_volume",
                     "short_vol_ratio", "short_interest", "days_to_cover"],
                    rows)
        print(f"  FINRA short interest: {len(rows)} symbols")
    else:
        # Try FINRA RegSHO daily data
        data = _fetch_finra_regsho()
        regsho_rows = []
        today = date.today().isoformat()
        if data and isinstance(data, list):
            for d in data:
                sym = d.get("issueSymbolIdentifier", "")
                total = d.get("totalParValue")
                short = d.get("shortParValue")
                ratio = (short / total) if total and short and total > 0 else None
                if sym:
                    regsho_rows.append((sym, today, short, total, ratio, None, None))
        if regsho_rows:
            upsert_many("finra_short_interest",
                        ["symbol", "date", "short_volume", "total_volume",
                         "short_vol_ratio", "short_interest", "days_to_cover"],
                        regsho_rows)
        print(f"  FINRA RegSHO: {len(regsho_rows)} symbols")
