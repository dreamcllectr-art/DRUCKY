"""Fetch OHLCV price data for stocks, crypto, and commodities."""

import time
import yfinance as yf
import pandas as pd
from tools.config import (
    COMMODITIES, CRYPTO_TICKERS, BENCHMARK_STOCK, BENCHMARK_DOLLAR,
    VIX_TICKER, VIX3M_TICKER, PRICE_HISTORY_DAYS, CROSS_ASSET_ETFS,
)
from tools.db import init_db, upsert_many, query


def get_stock_symbols():
    """Get stock symbols from the database."""
    rows = query("SELECT symbol FROM stock_universe")
    return [r["symbol"] for r in rows]


def fetch_batch(tickers, asset_class, period="1y"):
    """Download price data for a batch of tickers via yfinance."""
    if not tickers:
        return []

    rows = []
    # yfinance handles batches efficiently with multi-download
    batch_size = 100
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        ticker_str = " ".join(batch)
        try:
            data = yf.download(ticker_str, period=period, progress=False, threads=True)
            if data.empty:
                continue

            # Handle single vs multi-ticker DataFrames
            if len(batch) == 1:
                symbol = batch[0]
                for date_idx, row in data.iterrows():
                    date_str = date_idx.strftime("%Y-%m-%d")
                    rows.append((
                        symbol, date_str,
                        round(float(row["Open"]), 4) if pd.notna(row["Open"]) else None,
                        round(float(row["High"]), 4) if pd.notna(row["High"]) else None,
                        round(float(row["Low"]), 4) if pd.notna(row["Low"]) else None,
                        round(float(row["Close"]), 4) if pd.notna(row["Close"]) else None,
                        int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
                        asset_class,
                    ))
            else:
                for symbol in batch:
                    try:
                        sym_data = data.xs(symbol, level=1, axis=1) if isinstance(data.columns, pd.MultiIndex) else data
                        for date_idx, row in sym_data.iterrows():
                            if pd.isna(row.get("Close")):
                                continue
                            date_str = date_idx.strftime("%Y-%m-%d")
                            rows.append((
                                symbol, date_str,
                                round(float(row["Open"]), 4) if pd.notna(row["Open"]) else None,
                                round(float(row["High"]), 4) if pd.notna(row["High"]) else None,
                                round(float(row["Low"]), 4) if pd.notna(row["Low"]) else None,
                                round(float(row["Close"]), 4) if pd.notna(row["Close"]) else None,
                                int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
                                asset_class,
                            ))
                    except (KeyError, ValueError):
                        continue
        except Exception as e:
            print(f"  Warning: batch download failed for {batch[:3]}...: {e}")

        if i + batch_size < len(tickers):
            time.sleep(1)  # Rate limit respect

    return rows


def run():
    """Fetch all price data."""
    init_db()
    columns = ["symbol", "date", "open", "high", "low", "close", "volume", "asset_class"]

    # 1. Stocks
    stock_symbols = get_stock_symbols()
    if stock_symbols:
        print(f"Fetching prices for {len(stock_symbols)} stocks...")
        stock_rows = fetch_batch(stock_symbols, "stock")
        upsert_many("price_data", columns, stock_rows)
        print(f"  Saved {len(stock_rows)} stock price rows")

    # 2. Crypto
    crypto_tickers = list(CRYPTO_TICKERS.keys())
    print(f"Fetching prices for {len(crypto_tickers)} crypto assets...")
    crypto_rows = fetch_batch(crypto_tickers, "crypto")
    upsert_many("price_data", columns, crypto_rows)
    print(f"  Saved {len(crypto_rows)} crypto price rows")

    # 3. Commodities
    commodity_tickers = list(COMMODITIES.keys())
    print(f"Fetching prices for {len(commodity_tickers)} commodities...")
    commodity_rows = fetch_batch(commodity_tickers, "commodity")
    upsert_many("price_data", columns, commodity_rows)
    print(f"  Saved {len(commodity_rows)} commodity price rows")

    # 4. Benchmarks & indicators
    benchmark_tickers = [BENCHMARK_STOCK, BENCHMARK_DOLLAR, VIX_TICKER, VIX3M_TICKER]
    print("Fetching benchmark & indicator prices...")
    bench_rows = fetch_batch(benchmark_tickers, "benchmark")
    upsert_many("price_data", columns, bench_rows)
    print(f"  Saved {len(bench_rows)} benchmark price rows")

    # 5. Cross-asset regime ETFs (TLT, IWM, XLY, XLP, GDX, GLD, EEM, QQQ)
    cross_asset_tickers = list(CROSS_ASSET_ETFS.keys())
    print(f"Fetching cross-asset regime ETFs ({', '.join(cross_asset_tickers)})...")
    cross_rows = fetch_batch(cross_asset_tickers, "benchmark")
    upsert_many("price_data", columns, cross_rows)
    print(f"  Saved {len(cross_rows)} cross-asset ETF price rows")

    total = len(stock_rows) + len(crypto_rows) + len(commodity_rows) + len(bench_rows) + len(cross_rows)
    print(f"Total: {total} price rows saved.")


if __name__ == "__main__":
    run()
