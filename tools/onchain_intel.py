"""On-Chain Intelligence — crypto assets only.

Combines Nansen + Etherscan + CoinGecko into per-asset on-chain score.
Table: onchain_scores
"""
import logging
from datetime import date
from tools.db import get_conn, query, upsert_many

logger = logging.getLogger(__name__)

CRYPTO_ASSETS = ["BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", "DOT-USD"]


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS onchain_scores (
    asset TEXT, date TEXT,
    whale_net_score REAL, exchange_flow_score REAL,
    smart_money_score REAL, fear_greed_adjusted_score REAL,
    composite REAL,
    PRIMARY KEY (asset, date)
);
    """)
    conn.commit()
    conn.close()


def _fear_greed_adjustment(fear_greed_idx, base_score):
    """Contrarian adjustment for fear/greed extremes."""
    if fear_greed_idx is None:
        return base_score
    if fear_greed_idx > 80:  # Extreme greed → contrarian warning
        return max(20, base_score - 20)
    elif fear_greed_idx < 20:  # Extreme fear → contrarian opportunity
        return min(80, base_score + 15)
    return base_score


def run():
    _ensure_tables()
    today = date.today().isoformat()

    # Load Nansen signals
    nansen = {r["asset"]: r for r in query(
        """SELECT asset, smart_money_flow, whale_net, defi_tvl_change, score
           FROM nansen_signals WHERE date = (SELECT MAX(date) FROM nansen_signals)"""
    )}

    # Load Etherscan signals (global ETH metrics)
    eth_signals = query(
        "SELECT * FROM etherscan_signals ORDER BY date DESC LIMIT 1"
    )
    eth_data = eth_signals[0] if eth_signals else {}

    # Load CoinGecko data
    cg = {r["asset"]: r for r in query(
        """SELECT asset, price, volume, market_cap, fear_greed_idx,
                  dominance_pct, price_change_24h, price_change_7d
           FROM coingecko_data WHERE date = (SELECT MAX(date) FROM coingecko_data)"""
    )}

    rows = []
    for asset in CRYPTO_ASSETS:
        nan = nansen.get(asset, {})
        cg_d = cg.get(asset, {})
        fear_greed = cg_d.get("fear_greed_idx", 50) or 50

        # Whale net score (from Nansen)
        whale_net = nan.get("whale_net")
        whale_net_score = 50.0
        if whale_net is not None:
            whale_net_score = min(100, max(0, 50 + whale_net / 1e6 * 5))

        # Exchange flow score (from Etherscan for ETH, neutral for others)
        exchange_flow_score = 50.0
        if asset == "ETH-USD" and eth_data:
            net_flow = eth_data.get("net_exchange_flow_eth", 0) or 0
            exchange_flow_score = 65.0 if net_flow < 0 else 35.0

        # Smart money score (from Nansen)
        smart_money_score = nan.get("score", 50.0) or 50.0

        # Price momentum component
        change_24h = cg_d.get("price_change_24h", 0) or 0
        change_7d = cg_d.get("price_change_7d", 0) or 0
        momentum_score = 50 + change_24h * 0.5 + change_7d * 0.3
        momentum_score = max(0, min(100, momentum_score))

        # Raw composite (before fear/greed adjustment)
        raw_composite = (
            whale_net_score * 0.25 +
            exchange_flow_score * 0.20 +
            smart_money_score * 0.35 +
            momentum_score * 0.20
        )

        # Apply fear/greed contrarian adjustment
        adjusted = _fear_greed_adjustment(fear_greed, raw_composite)

        rows.append((asset, today, round(whale_net_score, 1), round(exchange_flow_score, 1),
                     round(smart_money_score, 1), round(adjusted, 1), round(adjusted, 1)))

    if rows:
        upsert_many("onchain_scores",
                    ["asset", "date", "whale_net_score", "exchange_flow_score",
                     "smart_money_score", "fear_greed_adjusted_score", "composite"],
                    rows)

    print(f"  On-chain Intel: {len(rows)} crypto assets scored")
    for r in rows:
        print(f"    {r[0]}: composite={r[6]:.0f}")
