"""Auto paper-trader — adds HIGH conviction signals to the portfolio.

After the convergence engine runs, this module:
  1. Reads all HIGH conviction signals from today
  2. Checks which ones are NOT already in the portfolio (open)
  3. Adds new entries as paper trades with entry price, stop, and target
  4. Checks existing open positions — closes any that hit stop or target
  5. Logs a daily P&L snapshot for performance tracking

This lets you measure how well the system actually performs over time.

Usage: python -m tools.paper_trader
Runs as Phase 3.98 in the daily pipeline (after convergence, before alerts).
"""

from datetime import date, datetime
from tools.db import query, get_conn, init_db

# Position sizing for paper trades (fixed notional per trade)
PAPER_PORTFOLIO_VALUE = 100_000  # Total paper portfolio
MAX_POSITIONS = 20               # Max concurrent open positions
POSITION_SIZE = PAPER_PORTFOLIO_VALUE / MAX_POSITIONS  # $5k per position


def _get_open_symbols() -> set:
    """Get symbols with open paper positions."""
    rows = query("SELECT symbol FROM portfolio WHERE status = 'open'")
    return {r["symbol"] for r in rows}


def _get_latest_price(symbol: str) -> float | None:
    """Get latest closing price for a symbol."""
    rows = query(
        "SELECT close FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 1",
        [symbol],
    )
    return rows[0]["close"] if rows else None


def _open_positions():
    """Open paper positions for new HIGH convergence signals."""
    today = date.today().isoformat()
    open_symbols = _get_open_symbols()
    open_count = len(open_symbols)

    # Get today's HIGH conviction signals (not forensic-blocked)
    signals = query(
        """SELECT c.symbol, c.convergence_score, c.conviction_level,
                  c.module_count, c.active_modules,
                  s.entry_price, s.stop_loss, s.target_price, s.signal
           FROM convergence_signals c
           LEFT JOIN signals s ON c.symbol = s.symbol
               AND s.date = (SELECT MAX(date) FROM signals WHERE symbol = s.symbol)
           WHERE c.date = (SELECT MAX(date) FROM convergence_signals)
             AND c.forensic_blocked = 0
             AND c.conviction_level = 'HIGH'
             AND s.signal IN ('strong_buy', 'buy')
           ORDER BY c.convergence_score DESC"""
    )

    new_trades = 0
    with get_conn() as conn:
        for sig in signals:
            symbol = sig["symbol"]

            # Skip if already in portfolio
            if symbol in open_symbols:
                continue

            # Respect max positions
            if open_count + new_trades >= MAX_POSITIONS:
                print(f"  Max positions ({MAX_POSITIONS}) reached, skipping remaining")
                break

            entry = sig["entry_price"]
            stop = sig["stop_loss"]
            target = sig["target_price"]

            if not entry or entry <= 0:
                price = _get_latest_price(symbol)
                if not price:
                    continue
                entry = price

            # Calculate shares from fixed position size
            shares = round(POSITION_SIZE / entry, 2)

            conn.execute(
                """INSERT INTO portfolio
                   (symbol, asset_class, entry_date, entry_price, shares,
                    stop_loss, target_price, status)
                   VALUES (?, 'stock', ?, ?, ?, ?, ?, 'open')""",
                (symbol, today, round(entry, 2), shares,
                 round(stop, 2) if stop else None,
                 round(target, 2) if target else None),
            )
            new_trades += 1
            direction = "▲" if sig["signal"] == "strong_buy" else "△"
            print(f"  {direction} OPENED {symbol} @ ${entry:.2f} "
                  f"(stop=${stop:.2f}, target=${target:.2f}, "
                  f"score={sig['convergence_score']:.0f}, "
                  f"modules={sig['module_count']})")

    if new_trades == 0:
        print("  No new HIGH signals to add")
    else:
        print(f"  Opened {new_trades} new paper positions")


def _check_exits():
    """Close positions that hit stop loss or target price."""
    today = date.today().isoformat()
    positions = query("SELECT * FROM portfolio WHERE status = 'open'")
    closed = 0

    with get_conn() as conn:
        for pos in positions:
            symbol = pos["symbol"]
            current = _get_latest_price(symbol)
            if not current:
                continue

            entry = pos["entry_price"]
            stop = pos["stop_loss"]
            target = pos["target_price"]
            reason = None

            # Check stop loss
            if stop and current <= stop:
                reason = "STOP"

            # Check target hit
            if target and current >= target:
                reason = "TARGET"

            # Check if conviction dropped (no longer HIGH or removed from convergence)
            if not reason:
                conv = query(
                    """SELECT conviction_level, forensic_blocked
                       FROM convergence_signals
                       WHERE symbol = ?
                       ORDER BY date DESC LIMIT 1""",
                    [symbol],
                )
                if conv:
                    c = conv[0]
                    if c["forensic_blocked"]:
                        reason = "FORENSIC_BLOCK"
                    elif c["conviction_level"] not in ("HIGH", "NOTABLE"):
                        reason = "CONVICTION_DROP"

            if reason:
                pnl = (current - entry) * pos["shares"]
                pnl_pct = ((current - entry) / entry) * 100

                conn.execute(
                    """UPDATE portfolio
                       SET status = 'closed', exit_date = ?, exit_price = ?,
                           pnl = ?, pnl_pct = ?
                       WHERE id = ?""",
                    (today, round(current, 2), round(pnl, 2),
                     round(pnl_pct, 2), pos["id"]),
                )
                icon = "✓" if pnl >= 0 else "✗"
                print(f"  {icon} CLOSED {symbol} @ ${current:.2f} "
                      f"({reason}, P&L: ${pnl:+.2f} / {pnl_pct:+.1f}%)")
                closed += 1

    if closed == 0:
        print("  No exits triggered")
    else:
        print(f"  Closed {closed} positions")


def _print_summary():
    """Print paper portfolio performance summary."""
    open_pos = query("SELECT * FROM portfolio WHERE status = 'open'")
    closed_pos = query("SELECT * FROM portfolio WHERE status = 'closed'")

    total_open_pnl = 0.0
    for pos in open_pos:
        current = _get_latest_price(pos["symbol"])
        if current and pos["entry_price"]:
            total_open_pnl += (current - pos["entry_price"]) * pos["shares"]

    total_closed_pnl = sum(p["pnl"] or 0 for p in closed_pos)
    wins = sum(1 for p in closed_pos if (p["pnl"] or 0) > 0)
    losses = sum(1 for p in closed_pos if (p["pnl"] or 0) <= 0)
    win_rate = (wins / len(closed_pos) * 100) if closed_pos else 0

    print(f"\n  ── PAPER PORTFOLIO SUMMARY ──")
    print(f"  Open positions:  {len(open_pos)}")
    print(f"  Open P&L:        ${total_open_pnl:+,.2f}")
    print(f"  Closed trades:   {len(closed_pos)} ({wins}W / {losses}L)")
    print(f"  Closed P&L:      ${total_closed_pnl:+,.2f}")
    print(f"  Win rate:        {win_rate:.0f}%")
    print(f"  Total P&L:       ${total_open_pnl + total_closed_pnl:+,.2f}")


def run():
    """Main entry point for daily pipeline."""
    print("\n  ── Paper Trader ──")
    _check_exits()
    _open_positions()
    _print_summary()


if __name__ == "__main__":
    init_db()
    run()
