"""FMP v2 — Financial Modeling Prep deep integration.

Fetches: short interest, institutional ownership, analyst grades,
DCF fair value, EPS consensus estimates.
Tables: fmp_short_interest, fmp_analyst_data, fmp_dcf, fmp_institutional
"""
import logging
import time
import requests
from datetime import date
from tools.db import get_conn, query, upsert_many
from tools.config import FMP_API_KEY

logger = logging.getLogger(__name__)

FMP_BASE_V3 = "https://financialmodelingprep.com/api/v3"
FMP_BASE_V4 = "https://financialmodelingprep.com/api/v4"
BATCH_DELAY = 0.12  # ~8 req/sec


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS fmp_short_interest (
    symbol TEXT, date TEXT,
    short_interest REAL, short_float_pct REAL, days_to_cover REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS fmp_analyst_data (
    symbol TEXT, date TEXT,
    analyst_count INTEGER, strong_buy INTEGER, buy INTEGER, hold INTEGER,
    sell INTEGER, strong_sell INTEGER, consensus TEXT,
    price_target REAL, price_target_high REAL, price_target_low REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS fmp_dcf (
    symbol TEXT, date TEXT,
    dcf_value REAL, stock_price REAL, upside_pct REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS fmp_institutional (
    symbol TEXT, date TEXT,
    institutional_pct REAL, institution_count INTEGER,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _get(url, params=None):
    p = {"apikey": FMP_API_KEY}
    if params:
        p.update(params)
    try:
        r = requests.get(url, params=p, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"FMP request failed {url}: {e}")
        return None


def _fetch_short_interest(symbols):
    today = date.today().isoformat()
    rows = []
    for sym in symbols:
        data = _get(f"{FMP_BASE_V4}/short-interest", {"symbol": sym})
        if data and isinstance(data, list) and data:
            d = data[0]
            rows.append((
                sym, today,
                d.get("shortInterest"), d.get("shortFloatPercent"),
                d.get("daysToCover"),
            ))
        time.sleep(BATCH_DELAY)
    upsert_many("fmp_short_interest",
                ["symbol", "date", "short_interest", "short_float_pct", "days_to_cover"],
                rows)
    return len(rows)


def _fetch_analyst_data(symbols):
    today = date.today().isoformat()
    rows = []
    for sym in symbols:
        data = _get(f"{FMP_BASE_V3}/analyst-stock-recommendations/{sym}", {"limit": 1})
        pt_data = _get(f"{FMP_BASE_V3}/price-target-consensus/{sym}")
        if data and isinstance(data, list) and data:
            d = data[0]
            pt = pt_data[0] if pt_data and isinstance(pt_data, list) and pt_data else {}
            # Map consensus text
            consensus = d.get("analystRatingsbuy", 0)
            rows.append((
                sym, today,
                d.get("analystRatingsTotalCount", 0),
                d.get("analystRatingsStrongBuy", 0),
                d.get("analystRatingsbuy", 0),
                d.get("analystRatingsHold", 0),
                d.get("analystRatingsSell", 0),
                d.get("analystRatingsStrongSell", 0),
                d.get("consensus", ""),
                pt.get("targetConsensus"), pt.get("targetHigh"), pt.get("targetLow"),
            ))
        time.sleep(BATCH_DELAY)
    upsert_many("fmp_analyst_data",
                ["symbol", "date", "analyst_count", "strong_buy", "buy", "hold",
                 "sell", "strong_sell", "consensus", "price_target",
                 "price_target_high", "price_target_low"],
                rows)
    return len(rows)


def _fetch_dcf(symbols):
    today = date.today().isoformat()
    rows = []
    for sym in symbols:
        data = _get(f"{FMP_BASE_V3}/discounted-cash-flow/{sym}")
        if data and isinstance(data, list) and data:
            d = data[0]
            dcf = d.get("dcf")
            price = d.get("Stock Price")
            upside = ((dcf / price) - 1) * 100 if dcf and price and price > 0 else None
            rows.append((sym, today, dcf, price, upside))
        time.sleep(BATCH_DELAY)
    upsert_many("fmp_dcf", ["symbol", "date", "dcf_value", "stock_price", "upside_pct"], rows)
    return len(rows)


def _fetch_institutional(symbols):
    today = date.today().isoformat()
    rows = []
    for sym in symbols:
        data = _get(f"{FMP_BASE_V4}/institutional-ownership/symbol-ownership",
                    {"symbol": sym, "includeCurrentQuarter": "true"})
        if data and isinstance(data, list) and data:
            d = data[0]
            rows.append((
                sym, today,
                d.get("percentOwned", 0) * 100 if d.get("percentOwned") else None,
                d.get("numberOfInstitutionalInvestors"),
            ))
        time.sleep(BATCH_DELAY)
    upsert_many("fmp_institutional",
                ["symbol", "date", "institutional_pct", "institution_count"], rows)
    return len(rows)


def run():
    if not FMP_API_KEY:
        print("  FMP API key not set — skipping")
        return

    _ensure_tables()
    symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
    if not symbols:
        print("  No symbols in universe — skipping FMP v2")
        return

    print(f"  Fetching FMP v2 data for {len(symbols)} symbols...")

    # Run all 4 fetches
    n1 = _fetch_short_interest(symbols)
    print(f"    Short interest: {n1} rows")

    n2 = _fetch_analyst_data(symbols)
    print(f"    Analyst data: {n2} rows")

    n3 = _fetch_dcf(symbols)
    print(f"    DCF: {n3} rows")

    n4 = _fetch_institutional(symbols)
    print(f"    Institutional: {n4} rows")

    print(f"  FMP v2 complete: {n1+n2+n3+n4} total rows")
