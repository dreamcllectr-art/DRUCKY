"""USDA agricultural data fetcher.

Key: 4FEC8DDE-2CA1-3BED-A976-11A66470184C
Data: Crop production, inventory, export sales for corn/wheat/soybeans.
Table: usda_commodity_data
"""
import logging
import time
import requests
from datetime import date
from tools.db import get_conn, upsert_many
from tools.config import USDA_API_KEY

logger = logging.getLogger(__name__)

USDA_NASS_BASE = "https://quickstats.nass.usda.gov/api"
USDA_ERS_BASE = "https://api.ers.usda.gov/data"
REQUEST_DELAY = 0.5


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS usda_commodity_data (
    commodity TEXT, date TEXT,
    production REAL, stocks REAL, exports REAL,
    price REAL, score REAL,
    PRIMARY KEY (commodity, date)
);
    """)
    conn.commit()
    conn.close()


def _get_nass(params):
    p = {"key": USDA_API_KEY, "format": "JSON"}
    p.update(params)
    try:
        r = requests.get(f"{USDA_NASS_BASE}/api_GET/", params=p, timeout=20)
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as e:
        logger.debug(f"USDA NASS failed: {e}")
        return []


def _fetch_commodity(commodity_name, short_desc_production, short_desc_stocks):
    """Fetch production and stocks for a commodity."""
    current_year = date.today().year
    production_data = _get_nass({
        "commodity_desc": commodity_name,
        "short_desc": short_desc_production,
        "year__GE": current_year - 1,
        "statisticcat_desc": "PRODUCTION",
        "unit_desc": "BU",
    })
    time.sleep(REQUEST_DELAY)

    stocks_data = _get_nass({
        "commodity_desc": commodity_name,
        "statisticcat_desc": "STOCKS",
        "year__GE": current_year - 1,
        "unit_desc": "BU",
    })
    time.sleep(REQUEST_DELAY)

    production = None
    if production_data:
        try:
            production = float(production_data[0].get("Value", "0").replace(",", ""))
        except (ValueError, IndexError):
            pass

    stocks = None
    if stocks_data:
        try:
            stocks = float(stocks_data[0].get("Value", "0").replace(",", ""))
        except (ValueError, IndexError):
            pass

    return production, stocks


def _score_commodity(production, stocks, commodity):
    """Simple supply/demand score (0-100). Higher = bullish for agri commodity."""
    score = 50.0
    if stocks is not None and production is not None and production > 0:
        stocks_to_use = stocks / production
        # Low stocks-to-use = supply tight = bullish
        if stocks_to_use < 0.10:
            score += 25
        elif stocks_to_use < 0.15:
            score += 15
        elif stocks_to_use > 0.30:
            score -= 15
        elif stocks_to_use > 0.40:
            score -= 25
    return round(max(0, min(100, score)), 1)


def run():
    if not USDA_API_KEY:
        print("  USDA API key not set — skipping")
        return

    _ensure_tables()
    today = date.today().isoformat()

    COMMODITIES = [
        ("CORN", "CORN - PRODUCTION, MEASURED IN BU", "CORN, GRAIN - STOCKS"),
        ("WHEAT", "WHEAT - PRODUCTION, MEASURED IN BU", "WHEAT - STOCKS"),
        ("SOYBEANS", "SOYBEANS - PRODUCTION, MEASURED IN BU", "SOYBEANS - STOCKS"),
    ]

    rows = []
    print(f"  Fetching USDA data for {len(COMMODITIES)} commodities...")

    for commodity, prod_desc, stocks_desc in COMMODITIES:
        production, stocks = _fetch_commodity(commodity, prod_desc, stocks_desc)
        score = _score_commodity(production, stocks, commodity)
        rows.append((commodity, today, production, stocks, None, None, score))

    if rows:
        upsert_many("usda_commodity_data",
                    ["commodity", "date", "production", "stocks", "exports", "price", "score"],
                    rows)
    print(f"  USDA: {len(rows)} commodity datasets updated")
