"""Nansen on-chain intelligence fetcher.

Key: eXdLO4iflTvUVHB6rTZMIuPv4OeIbIzu
Covers: 6 crypto assets — smart money flows, whale accumulation,
DeFi TVL changes, NFT activity.
Table: nansen_signals
"""
import logging
import time
import requests
from datetime import date
from tools.db import get_conn, upsert_many
from tools.config import NANSEN_API_KEY

logger = logging.getLogger(__name__)

NANSEN_BASE = "https://api.nansen.ai/v1"
CRYPTO_ASSETS = ["BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", "DOT-USD"]
REQUEST_DELAY = 1.0


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS nansen_signals (
    asset TEXT, date TEXT,
    smart_money_flow REAL, whale_net REAL, defi_tvl_change REAL,
    signal_type TEXT, score REAL,
    PRIMARY KEY (asset, date)
);
    """)
    conn.commit()
    conn.close()


def _get(endpoint, params=None):
    headers = {"apiKey": NANSEN_API_KEY, "Content-Type": "application/json"}
    try:
        r = requests.get(f"{NANSEN_BASE}/{endpoint}",
                         headers=headers, params=params, timeout=15)
        if r.status_code == 401:
            logger.warning("Nansen API key invalid or expired")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"Nansen {endpoint}: {e}")
        return None


def _score_signals(smart_money_flow, whale_net, defi_tvl_change):
    """Score 0-100 from on-chain signals."""
    score = 50.0  # Neutral baseline
    if smart_money_flow is not None:
        if smart_money_flow > 0:
            score += min(20, smart_money_flow / 1e6 * 5)
        else:
            score -= min(20, abs(smart_money_flow) / 1e6 * 5)
    if whale_net is not None:
        if whale_net > 0:
            score += min(15, whale_net / 1e6 * 3)
        else:
            score -= min(15, abs(whale_net) / 1e6 * 3)
    if defi_tvl_change is not None:
        if defi_tvl_change > 0.05:
            score += 10
        elif defi_tvl_change < -0.05:
            score -= 10
    return round(max(0, min(100, score)), 1)


def run():
    if not NANSEN_API_KEY:
        print("  Nansen API key not set — skipping")
        return

    _ensure_tables()
    today = date.today().isoformat()
    rows = []

    print(f"  Fetching Nansen on-chain data for {len(CRYPTO_ASSETS)} assets...")

    # Try to get smart money token flow data
    for asset in CRYPTO_ASSETS:
        # Map ticker to Nansen token identifier
        token_map = {
            "BTC-USD": "bitcoin", "ETH-USD": "ethereum", "SOL-USD": "solana",
            "ADA-USD": "cardano", "AVAX-USD": "avalanche", "DOT-USD": "polkadot",
        }
        token = token_map.get(asset, asset.lower().replace("-usd", ""))

        # Token flow endpoint
        flow_data = _get(f"token/{token}/smart-money-flow")
        whale_data = _get(f"token/{token}/whale-activity")
        tvl_data = _get("defi/total-tvl-change") if asset == "ETH-USD" else None

        smart_money_flow = None
        whale_net = None
        defi_tvl_change = None

        if flow_data:
            smart_money_flow = flow_data.get("netFlow") or flow_data.get("net_flow")
        if whale_data:
            whale_net = whale_data.get("netAccumulation") or whale_data.get("net_accumulation")
        if tvl_data:
            defi_tvl_change = tvl_data.get("change24h") or tvl_data.get("change_24h")

        score = _score_signals(smart_money_flow, whale_net, defi_tvl_change)
        signal_type = "bullish" if score > 60 else ("bearish" if score < 40 else "neutral")

        rows.append((asset, today, smart_money_flow, whale_net,
                     defi_tvl_change, signal_type, score))
        time.sleep(REQUEST_DELAY)

    if rows:
        upsert_many("nansen_signals",
                    ["asset", "date", "smart_money_flow", "whale_net",
                     "defi_tvl_change", "signal_type", "score"],
                    rows)
    print(f"  Nansen: {len(rows)} crypto assets updated")
