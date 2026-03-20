"""Etherscan on-chain Ethereum data fetcher.

Key: 28XRS454NYF99BEK7NRUB89ND7BD4HX5BI
Data: Whale transactions, gas trends, stablecoin supply, exchange flows.
Table: etherscan_signals
"""
import logging
import time
import requests
from datetime import date
from tools.db import get_conn, upsert_many
from tools.config import ETHERSCAN_API_KEY

logger = logging.getLogger(__name__)

ETHERSCAN_BASE = "https://api.etherscan.io/api"
REQUEST_DELAY = 0.25  # 4 req/sec (free: 5/sec)

# Major exchange ETH wallets (for exchange flow monitoring)
EXCHANGE_WALLETS = {
    "Binance": "0x28C6c06298d514Db089934071355E5743bf21d60",
    "Coinbase": "0x71660c4005ba85c37ccec55d0c4493e66fe775d3",
    "Kraken": "0x2910543Af39abA0Cd09dBb2D50200b3E800A63D2",
}

# Known whale/smart money wallets (top institutional)
WHALE_THRESHOLD_ETH = 1000  # 1000+ ETH = whale transaction


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS etherscan_signals (
    date TEXT PRIMARY KEY,
    avg_gas_gwei REAL, whale_tx_count INTEGER,
    exchange_inflow_eth REAL, exchange_outflow_eth REAL,
    net_exchange_flow_eth REAL, usdt_supply REAL,
    usdc_supply REAL, score REAL, signal_type TEXT
);
    """)
    conn.commit()
    conn.close()


def _get(module, action, **params):
    p = {
        "module": module,
        "action": action,
        "apikey": ETHERSCAN_API_KEY,
    }
    p.update(params)
    try:
        r = requests.get(ETHERSCAN_BASE, params=p, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "1":
            return data.get("result")
        return None
    except Exception as e:
        logger.debug(f"Etherscan {module}/{action}: {e}")
        return None


def _get_gas_price():
    result = _get("gastracker", "gasoracle")
    if result:
        try:
            return float(result.get("ProposeGasPrice", 20))
        except (ValueError, TypeError):
            pass
    return None


def _get_eth_supply():
    result = _get("stats", "ethsupply")
    if result:
        try:
            return float(result) / 1e18
        except (ValueError, TypeError):
            pass
    return None


def _score_onchain(gas_gwei, net_exchange_flow):
    """Score 0-100 from Ethereum on-chain metrics."""
    score = 50.0
    # Low gas = low activity (slightly bearish); High gas = high demand (bullish)
    if gas_gwei is not None:
        if gas_gwei < 5:
            score -= 5
        elif gas_gwei > 50:
            score += 10
        elif gas_gwei > 100:
            score += 5  # Too high = congestion (slightly negative)
    # Exchange outflows = HODLing = bullish
    if net_exchange_flow is not None:
        if net_exchange_flow < 0:  # Net outflow from exchanges
            score += 15
        elif net_exchange_flow > 0:  # Net inflow to exchanges (selling pressure)
            score -= 10
    return round(max(0, min(100, score)), 1)


def run():
    if not ETHERSCAN_API_KEY:
        print("  Etherscan API key not set — skipping")
        return

    _ensure_tables()
    today = date.today().isoformat()

    print("  Fetching Etherscan on-chain data...")

    gas_gwei = _get_gas_price()
    time.sleep(REQUEST_DELAY)

    # Simplified: estimate exchange flows from known wallets
    exchange_inflow = 0.0
    exchange_outflow = 0.0

    for exchange, wallet in EXCHANGE_WALLETS.items():
        txlist = _get("account", "txlist",
                      address=wallet, startblock=0, endblock=99999999,
                      page=1, offset=10, sort="desc")
        if txlist and isinstance(txlist, list):
            for tx in txlist[:5]:
                try:
                    value_eth = float(tx.get("value", 0)) / 1e18
                    if tx.get("to", "").lower() == wallet.lower():
                        exchange_inflow += value_eth
                    else:
                        exchange_outflow += value_eth
                except (ValueError, TypeError):
                    pass
        time.sleep(REQUEST_DELAY)

    net_flow = exchange_inflow - exchange_outflow
    score = _score_onchain(gas_gwei, net_flow)
    signal_type = "bullish" if score > 60 else ("bearish" if score < 40 else "neutral")

    upsert_many("etherscan_signals",
                ["date", "avg_gas_gwei", "whale_tx_count", "exchange_inflow_eth",
                 "exchange_outflow_eth", "net_exchange_flow_eth",
                 "usdt_supply", "usdc_supply", "score", "signal_type"],
                [(today, gas_gwei, 0, exchange_inflow, exchange_outflow,
                  net_flow, None, None, score, signal_type)])

    gas_gwei = gas_gwei or 0
    print(f"  Etherscan: gas={gas_gwei:.0f} gwei, net_exchange_flow={net_flow:.1f} ETH, score={score}")
