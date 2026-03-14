"""Position sizing engine (Druckenmiller-style).

Rules:
- Risk 1% per BUY, 2% per STRONG BUY
- Size = portfolio_value * risk% / (entry - stop)
- Liquidity cap: position <= 5% of 20-day ADV
- Single position cap: 20% of portfolio
- Gross exposure cap: 150%
"""

from tools.config import (
    PORTFOLIO_VALUE, RISK_PER_TRADE_BUY, RISK_PER_TRADE_STRONG,
    MAX_POSITION_PCT, LIQUIDITY_CAP_PCT, MAX_GROSS_EXPOSURE,
)
from tools.db import init_db, query_df, get_conn


def compute_position_sizes():
    """Calculate position sizes for all BUY/STRONG BUY signals."""
    init_db()
    print("Computing position sizes...")

    signals = query_df("""
        SELECT s.* FROM signals s
        INNER JOIN (SELECT symbol, MAX(date) as max_date FROM signals GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.max_date
        WHERE s.signal IN ('STRONG BUY', 'BUY')
        ORDER BY s.composite_score DESC
    """)

    if signals.empty:
        print("  No BUY signals to size.")
        return

    # Get avg daily volume for liquidity check
    adv_df = query_df("""
        SELECT symbol, AVG(volume * close) as avg_daily_value
        FROM price_data
        WHERE date >= date('now', '-30 days')
        GROUP BY symbol
    """)
    adv_map = dict(zip(adv_df["symbol"], adv_df["avg_daily_value"]))

    portfolio = PORTFOLIO_VALUE
    max_single = portfolio * MAX_POSITION_PCT
    max_gross = portfolio * MAX_GROSS_EXPOSURE
    total_exposure = 0

    updates = []
    for _, row in signals.iterrows():
        symbol = row["symbol"]
        signal = row["signal"]
        entry = float(row["entry_price"])
        stop = float(row["stop_loss"])

        if entry <= 0 or stop <= 0 or entry <= stop:
            continue

        risk_per_share = entry - stop
        risk_pct = RISK_PER_TRADE_STRONG if signal == "STRONG BUY" else RISK_PER_TRADE_BUY
        risk_dollars = portfolio * risk_pct

        # Base position size
        shares = risk_dollars / risk_per_share
        position_value = shares * entry

        # Cap: single position max
        if position_value > max_single:
            position_value = max_single
            shares = position_value / entry

        # Cap: liquidity
        adv = adv_map.get(symbol, 0)
        if adv > 0:
            max_by_liquidity = adv * LIQUIDITY_CAP_PCT
            if position_value > max_by_liquidity:
                position_value = max_by_liquidity
                shares = position_value / entry

        # Cap: gross exposure
        if total_exposure + position_value > max_gross:
            remaining = max_gross - total_exposure
            if remaining <= 0:
                continue
            position_value = remaining
            shares = position_value / entry

        total_exposure += position_value
        updates.append((round(shares, 2), round(position_value, 2), symbol, row["date"]))

    # Update signals table
    with get_conn() as conn:
        conn.executemany(
            """UPDATE signals SET position_size_shares = ?, position_size_dollars = ?
               WHERE symbol = ? AND date = ?""",
            updates
        )

    print(f"  Sized {len(updates)} positions")
    print(f"  Total exposure: ${total_exposure:,.0f} "
          f"({total_exposure / portfolio * 100:.0f}% of portfolio)")

    # Print sized positions
    for shares, dollars, symbol, date in updates[:15]:
        print(f"    {symbol:12s} | {shares:8.1f} shares | ${dollars:10,.0f}")


def run():
    compute_position_sizes()


if __name__ == "__main__":
    run()
