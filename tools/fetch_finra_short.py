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
    """Fetch RegSHO short volume data from FINRA API.
    Returns list of dicts with symbol, short_volume, total_volume, ratio."""
    url = "https://api.finra.org/data/group/otcMarket/name/regShoDaily"
    all_data = []
    for offset in range(0, 10000, 5000):
        try:
            r = requests.get(url, params={"limit": 5000, "offset": offset},
                             headers={"Accept": "application/json"}, timeout=30)
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            all_data.extend(batch)
            if len(batch) < 5000:
                break
            time.sleep(0.5)
        except Exception as e:
            logger.debug(f"FINRA RegSHO failed at offset {offset}: {e}")
            break
    return all_data


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
        # Primary source: FINRA RegSHO daily short volume (free, no key needed)
        data = _fetch_finra_regsho()
        regsho_rows = []
        today = date.today().isoformat()
        # Aggregate by symbol across reporting facilities
        sym_agg = {}
        if data and isinstance(data, list):
            for d in data:
                sym = d.get("securitiesInformationProcessorSymbolIdentifier", "")
                if not sym:
                    continue
                if sym not in sym_agg:
                    sym_agg[sym] = {"short": 0, "total": 0}
                sym_agg[sym]["short"] += d.get("shortParQuantity", 0) or 0
                sym_agg[sym]["total"] += d.get("totalParQuantity", 0) or 0
        for sym, agg in sym_agg.items():
            total = agg["total"]
            short = agg["short"]
            ratio = (short / total) if total > 0 else None
            regsho_rows.append((sym, today, short, total, ratio, None, None))
        if regsho_rows:
            upsert_many("finra_short_interest",
                        ["symbol", "date", "short_volume", "total_volume",
                         "short_vol_ratio", "short_interest", "days_to_cover"],
                        regsho_rows)
        print(f"  FINRA RegSHO: {len(regsho_rows)} symbols")
