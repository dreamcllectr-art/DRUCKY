"""Compute market breadth indicators from S&P 500 constituent data."""

import pandas as pd
from datetime import datetime
from tools.db import init_db, upsert_many, query_df


def compute_breadth():
    """Calculate market breadth metrics from stock price data."""
    # Get price data via JOIN — avoids 500-param IN clause incompatibility
    prices = query_df(
        """SELECT p.symbol, p.date, p.close
           FROM price_data p
           INNER JOIN stock_universe u ON p.symbol = u.symbol
           WHERE p.asset_class = 'stock'
           ORDER BY p.date"""
    )
    if prices.empty:
        return None

    pivot = prices.pivot(index="date", columns="symbol", values="close")
    pivot = pivot.sort_index()

    results = []
    dates = pivot.index.tolist()

    # Need at least 200 days for 200 DMA
    if len(dates) < 200:
        print("Not enough price history for breadth calculation")
        return None

    # Calculate 200-day moving average for each stock
    dma_200 = pivot.rolling(200).mean()

    # Process recent dates (last 60 trading days)
    for date in dates[-60:]:
        try:
            current_prices = pivot.loc[date].dropna()
            current_dma = dma_200.loc[date].dropna()

            # Stocks that have both price and DMA
            common = current_prices.index.intersection(current_dma.index)
            if len(common) < 50:
                continue

            above_200 = (current_prices[common] > current_dma[common]).sum()
            pct_above = above_200 / len(common) * 100

            # Daily returns for advance/decline
            if dates.index(date) > 0:
                prev_date = dates[dates.index(date) - 1]
                prev_prices = pivot.loc[prev_date].dropna()
                common_ret = current_prices.index.intersection(prev_prices.index)
                if len(common_ret) > 0:
                    returns = (current_prices[common_ret] / prev_prices[common_ret]) - 1
                    advances = (returns > 0).sum()
                    declines = (returns < 0).sum()
                    ad_ratio = advances / max(declines, 1)
                else:
                    ad_ratio = 1.0
            else:
                ad_ratio = 1.0

            # 52-week highs and lows (use up to 252 days of available history)
            date_idx = dates.index(date)
            lookback = min(252, date_idx)
            if lookback >= 60:  # need at least 60 days for meaningful highs/lows
                lookback_start = dates[date_idx - lookback]
                high_252 = pivot.loc[lookback_start:date].max()
                low_252 = pivot.loc[lookback_start:date].min()
                new_highs = (current_prices >= high_252 * 0.99).sum()
                new_lows = (current_prices <= low_252 * 1.01).sum()
            else:
                new_highs = 0
                new_lows = 0

            # Breadth score (0-20)
            breadth_score = 0.0
            if pct_above >= 70:
                breadth_score += 10
            elif pct_above >= 50:
                breadth_score += 5
            elif pct_above < 30:
                breadth_score -= 5

            if ad_ratio > 2:
                breadth_score += 5
            elif ad_ratio < 0.5:
                breadth_score -= 5

            if new_highs > new_lows:
                breadth_score += 5
            elif new_lows > new_highs:
                breadth_score -= 5

            breadth_score = max(0, min(20, breadth_score + 10))  # Shift to 0-20 range

            results.append((
                date, round(pct_above, 2), round(ad_ratio, 2),
                int(new_highs), int(new_lows), round(breadth_score, 2)
            ))
        except Exception:
            continue

    return results


def run():
    """Compute and store market breadth."""
    init_db()
    print("Computing market breadth indicators...")

    results = compute_breadth()
    if results:
        upsert_many(
            "market_breadth",
            ["date", "pct_above_200dma", "advance_decline_ratio",
             "new_highs", "new_lows", "breadth_score"],
            results
        )
        print(f"  Saved breadth data for {len(results)} dates")
        if results:
            latest = results[-1]
            print(f"  Latest: {latest[0]} | {latest[1]}% above 200 DMA | "
                  f"A/D ratio: {latest[2]} | Breadth score: {latest[5]}/20")
    else:
        print("  No breadth data computed (need price data first)")


if __name__ == "__main__":
    run()
