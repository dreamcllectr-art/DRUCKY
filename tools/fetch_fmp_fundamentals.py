"""Fetch fundamental data using yfinance (replaces deprecated FMP endpoints).

yfinance provides all key metrics for free:
- Valuation ratios (P/E, P/B, P/S, EV/EBITDA, FCF yield)
- Growth (revenue, earnings)
- Profitability (ROE, ROA, margins)
- Financial health (D/E, current ratio, interest coverage)
- Analyst ratings & price targets
- Insider transactions
"""

import time
import logging
import requests
import yfinance as yf
from tools.db import get_conn, query
from tools.config import FMP_API_KEY, FMP_BASE

logger = logging.getLogger(__name__)


def fmp_get(endpoint: str, params: dict = None):
    """Call FMP API v3. Returns parsed JSON or None on failure."""
    if not FMP_API_KEY:
        return None
    url = f"{FMP_BASE}{endpoint}"
    p = {"apikey": FMP_API_KEY}
    if params:
        p.update(params)
    try:
        resp = requests.get(url, params=p, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None

# Mapping: our metric name -> yfinance .info key
METRIC_MAP = {
    # Valuation
    "trailingPE": "trailingPE",
    "forwardPE": "forwardPE",
    "priceToBook": "priceToBook",
    "priceToSales": "priceToSalesTrailing12Months",
    "enterpriseToEbitda": "enterpriseToEbitda",
    "dividend_yield": "dividendYield",
    # Growth
    "revenue_growth": "revenueGrowth",
    "earnings_growth": "earningsGrowth",
    # Profitability
    "roe": "returnOnEquity",
    "roa": "returnOnAssets",
    "gross_margin": "grossMargins",
    "operating_margin": "operatingMargins",
    "profit_margin": "profitMargins",
    # Health
    "debt_equity": "debtToEquity",
    "current_ratio": "currentRatio",
    "quick_ratio": "quickRatio",
    # Analyst
    "analyst_target_consensus": "targetMeanPrice",
    "analyst_target_high": "targetHighPrice",
    "analyst_target_low": "targetLowPrice",
    "analyst_rating_count": "numberOfAnalystOpinions",
}


def _safe_get(info: dict, key: str):
    """Get a value from yfinance info, returning None for missing/invalid."""
    val = info.get(key)
    if val is None or val == "Infinity" or val == float("inf"):
        return None
    return val


def _fetch_analyst_breakdown(ticker_obj) -> dict:
    """Extract analyst buy/hold/sell percentages from recommendations."""
    try:
        rec = ticker_obj.recommendations
        if rec is None or rec.empty:
            return {}
        # Get the most recent recommendation summary
        latest = rec.iloc[-1] if len(rec) > 0 else None
        if latest is None:
            return {}
        # yfinance recommendations have columns like: strongBuy, buy, hold, sell, strongSell
        total = 0
        for col in ["strongBuy", "buy", "hold", "sell", "strongSell"]:
            if col in rec.columns:
                total += latest.get(col, 0) or 0
        if total == 0:
            return {}
        buy_count = (latest.get("strongBuy", 0) or 0) + (latest.get("buy", 0) or 0)
        sell_count = (latest.get("sell", 0) or 0) + (latest.get("strongSell", 0) or 0)
        return {
            "analyst_buy_pct": round(buy_count / total * 100, 1),
            "analyst_sell_pct": round(sell_count / total * 100, 1),
            "analyst_hold_pct": round((latest.get("hold", 0) or 0) / total * 100, 1),
        }
    except Exception:
        return {}


def _fetch_insider_data(ticker_obj) -> dict:
    """Extract net insider buying/selling from insider transactions."""
    try:
        insiders = ticker_obj.insider_transactions
        if insiders is None or insiders.empty:
            return {}
        # Filter to last 90 days
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=90)
        if "Start Date" in insiders.columns:
            insiders = insiders[insiders["Start Date"] >= cutoff]
        net_shares = 0
        net_value = 0
        for _, row in insiders.iterrows():
            shares = row.get("Shares", 0) or 0
            value = row.get("Value", 0) or 0
            tx_type = str(row.get("Transaction", "")).lower()
            if "sale" in tx_type or "sell" in tx_type:
                net_shares -= shares
                net_value -= value
            else:
                net_shares += shares
                net_value += value
        return {
            "insider_net_shares_90d": net_shares,
            "insider_net_value_90d": net_value,
        }
    except Exception:
        return {}


def run():
    """Fetch all fundamental data using yfinance."""
    symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
    if not symbols:
        print("  No stocks in universe. Run fetch_stock_universe.py first.")
        return

    print(f"Fetching yfinance fundamental data for {len(symbols)} stocks...")

    all_data = []  # list of (symbol, metric, value) tuples
    errors = 0
    batch_size = 50

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        if i > 0 and i % 200 == 0:
            print(f"    Progress: {i}/{len(symbols)} ({len(all_data)} data points)")

        for symbol in batch:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}

                if not info or "regularMarketPrice" not in info:
                    continue

                # Standard metrics from info dict
                for our_metric, yf_key in METRIC_MAP.items():
                    val = _safe_get(info, yf_key)
                    if val is not None:
                        # Convert percentages (yfinance returns 0.15 for 15%)
                        if our_metric in ("dividend_yield", "revenue_growth", "earnings_growth",
                                          "roe", "roa", "gross_margin", "operating_margin", "profit_margin"):
                            val = round(val * 100, 2) if abs(val) < 10 else round(val, 2)
                        all_data.append((symbol, our_metric, val))

                # Free cash flow yield (compute if not directly available)
                fcf = _safe_get(info, "freeCashflow")
                mcap = _safe_get(info, "marketCap")
                if fcf and mcap and mcap > 0:
                    all_data.append((symbol, "fcf_yield", round(fcf / mcap * 100, 2)))

                # Analyst breakdown
                analyst = _fetch_analyst_breakdown(ticker)
                for k, v in analyst.items():
                    all_data.append((symbol, k, v))

                # Insider data
                insider = _fetch_insider_data(ticker)
                for k, v in insider.items():
                    all_data.append((symbol, k, v))

            except Exception as e:
                errors += 1
                if errors <= 5:
                    logger.debug(f"  Error fetching {symbol}: {e}")

        # Small delay between batches to be respectful
        time.sleep(0.5)

    # Save to database
    if all_data:
        with get_conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO fundamentals (symbol, metric, value) VALUES (?, ?, ?)",
                all_data,
            )
        print(f"\n  Total: {len(all_data)} fundamental data points saved ({errors} errors).")
    else:
        print("  No fundamental data fetched.")
