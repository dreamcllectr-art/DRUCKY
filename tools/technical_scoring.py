"""Technical scoring engine (0-100) per asset.

5 sub-scores, each 0-20:
- Trend (price vs MAs, ADX)
- Momentum (RSI, MACD, ROC)
- Breakout (52w high proximity, volume surge, Bollinger squeeze)
- Relative Strength (vs benchmark)
- Market Breadth (applied uniformly)
"""

import numpy as np
import pandas as pd
import ta
from datetime import datetime
from tools.config import (
    BENCHMARK_STOCK, BENCHMARK_CRYPTO, BENCHMARK_DOLLAR,
    RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL, BB_PERIOD, BB_STD, ADX_PERIOD,
)
from tools.db import init_db, upsert_many, query_df


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _get_price_series(symbol, price_df):
    """Extract sorted price series for a symbol."""
    sub = price_df[price_df["symbol"] == symbol].sort_values("date").copy()
    if sub.empty:
        return None
    sub = sub.dropna(subset=["close"])
    sub = sub.reset_index(drop=True)
    return sub


def score_trend(df):
    """Trend score (0-20): price vs 50/200 DMA, golden cross, ADX."""
    if len(df) < 200:
        # Not enough data for 200 DMA
        if len(df) < 50:
            return 10  # neutral
        # Use shorter lookback
        dma50 = df["close"].rolling(50).mean()
        score = 10.0
        if df["close"].iloc[-1] > dma50.iloc[-1]:
            score += 5
        return _clamp(score, 0, 20)

    close = df["close"]
    dma50 = close.rolling(50).mean()
    dma200 = close.rolling(200).mean()

    score = 0.0
    current = close.iloc[-1]

    # Price vs 50 DMA
    if current > dma50.iloc[-1]:
        score += 5

    # Price vs 200 DMA
    if current > dma200.iloc[-1]:
        score += 5

    # Golden cross (50 > 200) vs death cross
    if dma50.iloc[-1] > dma200.iloc[-1]:
        score += 5

    # ADX strength
    try:
        adx = ta.trend.ADXIndicator(
            high=df["high"], low=df["low"], close=df["close"], window=ADX_PERIOD
        )
        adx_val = adx.adx().iloc[-1]
        if not np.isnan(adx_val):
            if adx_val > 25:
                score += 5  # Strong trend
            elif adx_val > 20:
                score += 3
    except Exception:
        pass

    return _clamp(score, 0, 20)


def score_momentum(df):
    """Momentum score (0-20): RSI, MACD histogram, ROC."""
    if len(df) < 30:
        return 10

    close = df["close"]
    score = 0.0

    # RSI
    try:
        rsi = ta.momentum.RSIIndicator(close=close, window=RSI_PERIOD)
        rsi_val = rsi.rsi().iloc[-1]
        if not np.isnan(rsi_val):
            if 50 <= rsi_val <= 70:
                score += 7  # Bullish momentum
            elif rsi_val > 70:
                score += 3  # Overbought but still up
            elif rsi_val < 30:
                score += 2  # Oversold (potential reversal)
            elif 30 <= rsi_val < 50:
                score += 0  # Weak
    except Exception:
        score += 3

    # MACD Histogram
    try:
        macd = ta.trend.MACD(close=close, window_fast=MACD_FAST,
                             window_slow=MACD_SLOW, window_sign=MACD_SIGNAL)
        hist = macd.macd_diff()
        if len(hist) >= 2:
            h_now = hist.iloc[-1]
            h_prev = hist.iloc[-2]
            if not np.isnan(h_now):
                if h_now > 0 and h_now > h_prev:
                    score += 7  # Positive and rising
                elif h_now > 0:
                    score += 4  # Positive
                elif h_now < 0 and h_now > h_prev:
                    score += 2  # Negative but improving
    except Exception:
        score += 3

    # Rate of Change (20-day)
    if len(close) >= 20:
        roc = ((close.iloc[-1] / close.iloc[-20]) - 1) * 100
        if roc > 10:
            score += 6
        elif roc > 5:
            score += 4
        elif roc > 0:
            score += 2

    return _clamp(score, 0, 20)


def score_breakout(df):
    """Breakout score (0-20): 52w high proximity, volume surge, BB squeeze."""
    if len(df) < 20:
        return 10

    close = df["close"]
    score = 0.0

    # 52-week high proximity
    lookback = min(252, len(close))
    high_52w = close.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    current = close.iloc[-1]

    if high_52w > 0:
        pct_from_high = ((high_52w - current) / high_52w) * 100
        if pct_from_high <= 5:
            score += 10  # Within 5% of 52w high
        elif pct_from_high <= 10:
            score += 5

    if low_52w > 0:
        pct_from_low = ((current - low_52w) / low_52w) * 100
        if pct_from_low <= 5:
            score -= 5  # Near 52w low

    # Volume surge
    if "volume" in df.columns and len(df) >= 20:
        vol = df["volume"]
        avg_vol = vol.iloc[-20:].mean()
        if avg_vol > 0 and vol.iloc[-1] > avg_vol * 2:
            score += 5  # Volume surge

    # Bollinger Band squeeze (low bandwidth = coiled spring)
    try:
        bb = ta.volatility.BollingerBands(close=close, window=BB_PERIOD, window_dev=BB_STD)
        bandwidth = bb.bollinger_wband()
        if len(bandwidth) >= 252:
            bw_pctile = (bandwidth.iloc[-1] <= bandwidth.iloc[-252:]).mean() * 100
            if bw_pctile <= 10:
                score += 5  # Squeeze
    except Exception:
        pass

    return _clamp(score, 0, 20)


def score_relative_strength(df, benchmark_df, months=3):
    """Relative strength vs benchmark (0-20)."""
    if df is None or benchmark_df is None:
        return 10

    trading_days = months * 21
    if len(df) < trading_days or len(benchmark_df) < trading_days:
        return 10

    asset_ret = (df["close"].iloc[-1] / df["close"].iloc[-trading_days] - 1)
    bench_ret = (benchmark_df["close"].iloc[-1] / benchmark_df["close"].iloc[-trading_days] - 1)
    excess = asset_ret - bench_ret

    # Map excess return to score
    if excess > 0.30:  # 30%+ outperformance
        return 20
    elif excess > 0.15:
        return 17
    elif excess > 0.05:
        return 14
    elif excess > 0:
        return 12
    elif excess > -0.10:
        return 8
    elif excess > -0.20:
        return 4
    else:
        return 0


def run():
    """Compute technical scores for all assets."""
    init_db()
    print("Computing technical scores...")

    price_df = query_df("SELECT * FROM price_data ORDER BY date")
    if price_df.empty:
        print("  No price data. Run fetch_prices.py first.")
        return

    # Get latest breadth score
    breadth_df = query_df("SELECT breadth_score FROM market_breadth ORDER BY date DESC LIMIT 1")
    breadth_score = float(breadth_df.iloc[0]["breadth_score"]) if not breadth_df.empty else 10.0

    # Load benchmarks
    spy_df = _get_price_series(BENCHMARK_STOCK, price_df)
    btc_df = _get_price_series(BENCHMARK_CRYPTO, price_df)
    dxy_df = _get_price_series(BENCHMARK_DOLLAR, price_df)

    # Get all unique symbols (exclude benchmarks)
    all_symbols = price_df[~price_df["asset_class"].isin(["benchmark"])]["symbol"].unique()
    today = datetime.now().strftime("%Y-%m-%d")

    results = []
    for i, symbol in enumerate(all_symbols):
        df = _get_price_series(symbol, price_df)
        if df is None or len(df) < 20:
            continue

        asset_class = df["asset_class"].iloc[0]

        t = score_trend(df)
        m = score_momentum(df)
        b = score_breakout(df)

        # Pick correct benchmark for relative strength
        if asset_class == "crypto":
            bench = btc_df
        elif asset_class == "commodity":
            # For commodities, inverse DXY relationship
            bench = spy_df  # Use SPY as fallback
        else:
            bench = spy_df
        rs = score_relative_strength(df, bench)

        total = t + m + b + rs + breadth_score

        results.append((symbol, today, t, m, b, rs, breadth_score, round(total, 1)))

        if (i + 1) % 200 == 0:
            print(f"  Progress: {i + 1}/{len(all_symbols)}")

    upsert_many(
        "technical_scores",
        ["symbol", "date", "trend_score", "momentum_score", "breakout_score",
         "relative_strength_score", "breadth_score", "total_score"],
        results
    )
    print(f"  Computed technical scores for {len(results)} assets")

    # Show top 10
    if results:
        sorted_results = sorted(results, key=lambda x: x[-1], reverse=True)
        print("\n  Top 10 Technical Scores:")
        for r in sorted_results[:10]:
            print(f"    {r[0]:12s} | Total: {r[-1]:5.1f} | "
                  f"T:{r[2]:4.0f} M:{r[3]:4.0f} B:{r[4]:4.0f} RS:{r[5]:4.0f} Br:{r[6]:4.0f}")


if __name__ == "__main__":
    run()
