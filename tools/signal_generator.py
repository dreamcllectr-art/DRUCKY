"""Signal generator: combines macro + technical + fundamental into actionable signals.

Druckenmiller principle: "It's not whether you're right or wrong, but how much you
make when you're right and how much you lose when you're wrong."
"""

import numpy as np
import pandas as pd
from datetime import datetime
from tools.config import (
    REGIME_WEIGHTS, SIGNAL_THRESHOLDS, MIN_RR_RATIO, ATR_PERIOD,
)
from tools.db import init_db, upsert_many, query_df


def get_current_regime():
    """Get the latest macro regime and score."""
    df = query_df("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    if df.empty:
        return "neutral", 50
    row = df.iloc[0]
    return row["regime"], float(row["total_score"])


def normalize_macro_to_100(macro_score):
    """Convert macro score (-100 to +100) to 0-100 scale for blending."""
    return (macro_score + 100) / 2


def compute_atr(price_df, symbol, period=ATR_PERIOD):
    """Compute Average True Range for stop loss calculation."""
    df = price_df[price_df["symbol"] == symbol].sort_values("date").tail(period + 5)
    if len(df) < period:
        return None

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    tr = []
    for i in range(1, len(high)):
        tr.append(max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        ))

    if len(tr) < period:
        return None
    return np.mean(tr[-period:])


def compute_stop_loss(current_price, atr, dma50):
    """Compute stop loss: lower of 2x ATR or below 50 DMA."""
    stops = []
    if atr is not None:
        stops.append(current_price - 2 * atr)
    if dma50 is not None and dma50 > 0:
        stops.append(dma50 * 0.98)  # 2% below 50 DMA

    if not stops:
        return current_price * 0.90  # Fallback: 10% stop

    return max(min(stops), current_price * 0.70)  # Never more than 30% stop


def run():
    """Generate signals for all scored assets."""
    init_db()
    print("Generating signals...")

    regime, macro_total = get_current_regime()
    macro_normalized = normalize_macro_to_100(macro_total)
    weights = REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS["neutral"])
    macro_wt, tech_wt, fund_wt = weights

    print(f"  Regime: {regime} ({macro_total:+.0f}) | "
          f"Weights: Macro {macro_wt:.0%} Tech {tech_wt:.0%} Fund {fund_wt:.0%}")

    # Get latest scores
    tech_df = query_df("""
        SELECT t.* FROM technical_scores t
        INNER JOIN (SELECT symbol, MAX(date) as max_date FROM technical_scores GROUP BY symbol) m
        ON t.symbol = m.symbol AND t.date = m.max_date
    """)
    fund_df = query_df("""
        SELECT f.* FROM fundamental_scores f
        INNER JOIN (SELECT symbol, MAX(date) as max_date FROM fundamental_scores GROUP BY symbol) m
        ON f.symbol = m.symbol AND f.date = m.max_date
    """)
    price_df = query_df("SELECT * FROM price_data")

    if tech_df.empty:
        print("  No technical scores. Run technical_scoring.py first.")
        return

    # Get asset classes
    asset_classes = query_df(
        "SELECT DISTINCT symbol, asset_class FROM price_data"
    ).drop_duplicates(subset="symbol").set_index("symbol")["asset_class"].to_dict()

    today = datetime.now().strftime("%Y-%m-%d")
    results = []

    for _, tech_row in tech_df.iterrows():
        symbol = tech_row["symbol"]
        tech_score = float(tech_row["total_score"])
        asset_class = asset_classes.get(symbol, "stock")

        # Get fundamental score (default 50 for crypto/commodities)
        fund_row = fund_df[fund_df["symbol"] == symbol]
        if not fund_row.empty:
            fund_score = float(fund_row.iloc[0]["total_score"])
        else:
            fund_score = 50.0  # Neutral for crypto/commodities

        # Compute composite
        composite = (macro_normalized * macro_wt +
                     tech_score * tech_wt +
                     fund_score * fund_wt)

        # Classify signal
        if composite >= SIGNAL_THRESHOLDS["strong_buy"]:
            signal = "STRONG BUY"
        elif composite >= SIGNAL_THRESHOLDS["buy"]:
            signal = "BUY"
        elif composite >= SIGNAL_THRESHOLDS["neutral"]:
            signal = "NEUTRAL"
        elif composite >= SIGNAL_THRESHOLDS["sell"]:
            signal = "SELL"
        else:
            signal = "STRONG SELL"

        # Get current price
        sym_prices = price_df[price_df["symbol"] == symbol].sort_values("date")
        if sym_prices.empty:
            continue
        current_price = float(sym_prices.iloc[-1]["close"])

        if current_price <= 0:
            continue

        # Compute entry/stop/target
        entry_price = current_price
        atr = compute_atr(price_df, symbol)

        # 50 DMA
        if len(sym_prices) >= 50:
            dma50 = sym_prices["close"].tail(50).mean()
        else:
            dma50 = None

        stop_loss = compute_stop_loss(current_price, atr, dma50)
        risk = entry_price - stop_loss

        if risk <= 0:
            continue

        target_price = entry_price + MIN_RR_RATIO * risk
        rr_ratio = (target_price - entry_price) / risk if risk > 0 else 0

        results.append((
            symbol, today, asset_class,
            round(macro_normalized, 1), round(tech_score, 1), round(fund_score, 1),
            round(composite, 1), signal,
            round(entry_price, 4), round(stop_loss, 4), round(target_price, 4),
            round(rr_ratio, 2),
            None, None,  # Position size calculated separately
        ))

    upsert_many(
        "signals",
        ["symbol", "date", "asset_class", "macro_score", "technical_score",
         "fundamental_score", "composite_score", "signal",
         "entry_price", "stop_loss", "target_price", "rr_ratio",
         "position_size_shares", "position_size_dollars"],
        results
    )

    # Summary
    signal_counts = {}
    for r in results:
        sig = r[7]
        signal_counts[sig] = signal_counts.get(sig, 0) + 1

    print(f"\n  Generated {len(results)} signals:")
    for sig in ["STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"]:
        count = signal_counts.get(sig, 0)
        if count:
            print(f"    {sig:15s}: {count}")

    # Show top STRONG BUY / BUY
    buys = [r for r in results if r[7] in ("STRONG BUY", "BUY")]
    buys.sort(key=lambda x: x[6], reverse=True)
    if buys:
        print(f"\n  Top Buy Signals:")
        for r in buys[:15]:
            print(f"    {r[7]:11s} | {r[0]:12s} ({r[2]:9s}) | "
                  f"Score: {r[6]:5.1f} | Entry: {r[8]:10.2f} | "
                  f"Stop: {r[9]:10.2f} | Target: {r[10]:10.2f} | R:R {r[11]:.1f}")


if __name__ == "__main__":
    run()
