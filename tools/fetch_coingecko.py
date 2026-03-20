"""CoinGecko crypto market data fetcher.

No API key required. Public CoinGecko API.
Table: coingecko_data
"""
import logging
import time
import requests
from datetime import date
from tools.db import get_conn, upsert_many

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
REQUEST_DELAY = 1.5  # ~40 req/min free tier

# Mapping from CoinGecko ID to our ticker
CRYPTO_MAP = {
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "solana": "SOL-USD",
    "cardano": "ADA-USD",
    "avalanche-2": "AVAX-USD",
    "polkadot": "DOT-USD",
}


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS coingecko_data (
    asset TEXT, date TEXT,
    price REAL, volume REAL, market_cap REAL,
    dominance_pct REAL, fear_greed_idx REAL,
    price_change_24h REAL, price_change_7d REAL,
    PRIMARY KEY (asset, date)
);
    """)
    conn.commit()
    conn.close()


def _get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 429:
            time.sleep(60)
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"CoinGecko request failed {url}: {e}")
        return None


def _fetch_prices():
    ids = ",".join(CRYPTO_MAP.keys())
    data = _get(f"{COINGECKO_BASE}/coins/markets", {
        "vs_currency": "usd",
        "ids": ids,
        "price_change_percentage": "24h,7d",
    })
    return data or []


def _fetch_global():
    data = _get(f"{COINGECKO_BASE}/global")
    return data.get("data", {}) if data else {}


def _fetch_fear_greed():
    data = _get("https://api.alternative.me/fng/?limit=1")
    if data and data.get("data"):
        return float(data["data"][0].get("value", 50))
    return 50.0


def run():
    _ensure_tables()
    today = date.today().isoformat()

    print("  Fetching CoinGecko crypto data...")
    prices = _fetch_prices()
    time.sleep(REQUEST_DELAY)

    global_data = _fetch_global()
    time.sleep(REQUEST_DELAY)

    fear_greed = _fetch_fear_greed()
    time.sleep(REQUEST_DELAY)

    btc_dominance = global_data.get("bitcoin_dominance_percentage", 0)

    rows = []
    price_map = {p["id"]: p for p in prices}
    for cg_id, ticker in CRYPTO_MAP.items():
        p = price_map.get(cg_id, {})
        dominance = btc_dominance if cg_id == "bitcoin" else None
        rows.append((
            ticker, today,
            p.get("current_price"), p.get("total_volume"),
            p.get("market_cap"), dominance, fear_greed,
            p.get("price_change_percentage_24h"),
            p.get("price_change_percentage_7d_in_currency"),
        ))

    if rows:
        upsert_many("coingecko_data",
                    ["asset", "date", "price", "volume", "market_cap",
                     "dominance_pct", "fear_greed_idx",
                     "price_change_24h", "price_change_7d"],
                    rows)
    print(f"  CoinGecko: {len(rows)} crypto assets updated (fear/greed: {fear_greed:.0f})")
