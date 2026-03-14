"""Fetch fundamental data for stocks via yfinance."""

import time
import yfinance as yf
from tools.db import init_db, upsert_many, query


# yfinance field -> normalized metric name (matches scoring engine + FMP names)
METRIC_MAP = {
    "trailingPE":        "pe_ratio",
    "priceToBook":       "pb_ratio",
    "priceToSalesTrailing12Months": "ps_ratio",
    "dividendYield":     "dividend_yield",
    "revenueGrowth":     "revenue_growth",
    "earningsGrowth":    "earnings_growth",
    "returnOnEquity":    "roe",
    "returnOnAssets":    "roa",
    "grossMargins":      "gross_margin",
    "operatingMargins":  "operating_margin",
    "profitMargins":     "net_margin",
    "debtToEquity":      "debt_equity",
    "currentRatio":      "current_ratio",
    "quickRatio":        "quick_ratio",
    "marketCap":         "market_cap",
    "enterpriseValue":   "enterprise_value",
    "sharesOutstanding": "shares_outstanding",
    "heldPercentInsiders": "insider_pct",
}


def run():
    """Fetch fundamentals for all stocks in the universe."""
    init_db()

    symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
    if not symbols:
        print("No stocks in universe. Run fetch_stock_universe.py first.")
        return

    print(f"Fetching fundamentals for {len(symbols)} stocks...")
    rows = []
    errors = 0

    for i, symbol in enumerate(symbols):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            if not info or info.get("regularMarketPrice") is None:
                continue

            for yf_key, metric in METRIC_MAP.items():
                val = info.get(yf_key)
                if val is not None:
                    rows.append((symbol, metric, float(val)))

            # FCF yield = freeCashflow / marketCap
            fcf = info.get("freeCashflow")
            mcap = info.get("marketCap")
            if fcf and mcap and mcap > 0:
                rows.append((symbol, "fcf_yield", fcf / mcap))

            # Also store sector for sector comparisons
            sector = info.get("sector", "")
            if sector:
                rows.append((symbol, "sector_name", hash(sector) % 1000))

        except Exception:
            errors += 1

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{len(symbols)} ({errors} errors)")
            time.sleep(0.5)

    upsert_many("fundamentals", ["symbol", "metric", "value"], rows)
    print(f"Saved {len(rows)} fundamental data points ({errors} errors).")


if __name__ == "__main__":
    run()
